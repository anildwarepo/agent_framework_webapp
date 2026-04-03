# pg_age_helper.py

import os, asyncio, json, re, logging
import psycopg
from psycopg import sql
from psycopg.rows import dict_row   # 👈 NEW
from dotenv import load_dotenv
from typing import Any, List

logger = logging.getLogger("age_mcp")

load_dotenv()

DSN = dict(
    host=os.getenv("PGHOST", "localhost"),
    port=int(os.getenv("PGPORT", "5432")),
    dbname=os.getenv("PGDATABASE", "postgres"),
    user=os.getenv("PGUSER", "postgres"),
    password=os.getenv("PGPASSWORD", "postgres"),
    sslmode=os.getenv("PGSSLMODE", "require"),
)

GRAPH = os.getenv("GRAPH_NAME")

if not GRAPH:
    raise ValueError("GRAPH environment variable must be set")

print("Using graph:", GRAPH)
print("Using DSN:", {k: (v if k != "password" else "****") for k, v in DSN.items()})

class PGAgeHelper:
    def __init__(self, conn: psycopg.AsyncConnection):
        self._conn = conn
        self.graph = GRAPH

    @classmethod
    async def create(cls) -> "PGAgeHelper":
        conn = await cls._create_connection()
        return cls(conn)

    @classmethod
    async def _create_connection(cls) -> psycopg.AsyncConnection:
        """Create and initialize a new database connection."""
        # row_factory=dict_row -> rows become dicts instead of tuples
        conn = await psycopg.AsyncConnection.connect(**DSN, row_factory=dict_row)
        
        async with conn.cursor() as cur:
            # Check if AGE extension exists, create it if not
            await cur.execute("SELECT 1 FROM pg_extension WHERE extname='age';")
            if not await cur.fetchone():
                print("AGE extension not found, creating it...")
                try:
                    await cur.execute("CREATE EXTENSION IF NOT EXISTS age CASCADE;")
                    await conn.commit()
                    print("AGE extension created successfully")
                except Exception as e:
                    print(f"Warning: Could not create AGE extension: {e}")
                    # Check again after attempting creation
                    await cur.execute("SELECT 1 FROM pg_extension WHERE extname='age';")
                    if not await cur.fetchone():
                        await conn.close()
                        raise RuntimeError(
                            "AGE extension is not installed in this database and could not be created. "
                            "Run as superuser: CREATE EXTENSION age;"
                        )
            
            # Load AGE library (not needed if 'age' is in shared_preload_libraries)
            try:
                await cur.execute("LOAD 'age';")
            except psycopg.errors.InsufficientPrivilege:
                # On Azure PostgreSQL Flexible Server, LOAD is not allowed but
                # AGE is already loaded via shared_preload_libraries.
                await conn.rollback()
            
            await cur.execute('SET search_path = ag_catalog, "$user", public;')
            
            # Try to set search path for the database (requires permissions)
            try:
                await cur.execute('ALTER DATABASE postgres SET search_path = ag_catalog, "$user", public;')
                await conn.commit()
                print("Database search path configured")
            except Exception as e:
                print(f"Note: Could not set database-level search path (may require higher privileges): {e}")
            
            # Create graph if it doesn't exist
            try:
                await cur.execute(f"SELECT 1 FROM ag_catalog.ag_graph WHERE name = '{GRAPH}';")
                if not await cur.fetchone():
                    print(f"Graph '{GRAPH}' not found, creating it...")
                    await cur.execute(f"SELECT ag_catalog.create_graph('{GRAPH}');")
                    await conn.commit()
                    print(f"Graph '{GRAPH}' created successfully")
                else:
                    print(f"Graph '{GRAPH}' already exists")
            except Exception as e:
                print(f"Note: Could not check/create graph: {e}")

        return conn

    async def _ensure_connected(self) -> None:
        """Check if connection is alive and reconnect if needed."""
        try:
            # Check if connection is in a bad state
            if self._conn.closed or self._conn.broken:
                print("Connection is closed or broken, reconnecting...")
                await self._reconnect()
        except Exception as e:
            print(f"Connection check failed: {e}, attempting reconnect...")
            await self._reconnect()

    async def _reconnect(self) -> None:
        """Close existing connection (if any) and create a new one."""
        try:
            if self._conn and not self._conn.closed:
                await self._conn.close()
        except Exception as e:
            print(f"Error closing old connection: {e}")
        
        print("Creating new database connection...")
        self._conn = await self._create_connection()
        print("Reconnection successful")

    @staticmethod
    def _normalize_cypher_query(query: str, graph_name: str | None = None) -> str:
        """
        Sanitize common LLM-generated query mistakes for PostgreSQL AGE compatibility.
        """
        # 0. Detect cypher body passed without $$ wrapper
        #    Patterns LLMs generate:
        #      cypher('MATCH ...')                              — body as 1st arg
        #      cypher('MATCH ...', true) AS t                   — body as 1st arg + extra args
        #      cypher('graph_name', 'MATCH ...')                — correct args but single quotes
        #      cypher('graph_name', 'MATCH ...') AS (col ...)   — correct args, single quotes, has AS
        #    Fix: extract body, wrap with $$ + proper AS clause

        # Strip backslash-escaped quotes that some models produce: \' → '
        query = query.replace("\\'", "'")

        # Pattern A: cypher('graph_name', 'MATCH...') — body as 2nd arg in single quotes
        m_quoted_body = re.search(
            r"(?:ag_catalog\.)?cypher\s*\(\s*'([^']+)'\s*,\s*'((?:MATCH|WITH|UNWIND)\b.*?)'\s*\)\s*(?:AS\s*\([^)]*\)\s*)?;?\s*$",
            query, re.IGNORECASE | re.DOTALL
        )
        if m_quoted_body:
            gn = m_quoted_body.group(1)
            cypher_body = m_quoted_body.group(2).replace("''", "'")
            ret_match = re.search(r'RETURN\s+(.*?)$', cypher_body, re.IGNORECASE | re.DOTALL)
            if ret_match:
                aliases = re.findall(r'\bAS\s+(\w+)', ret_match.group(1).strip().rstrip(';'), re.IGNORECASE)
                if not aliases:
                    aliases = ["result"]
                as_cols = ", ".join(f"{a} ag_catalog.agtype" for a in aliases)
            else:
                as_cols = "result ag_catalog.agtype"
            query = f"SELECT * FROM ag_catalog.cypher('{gn}', $${cypher_body}$$) AS ({as_cols});"
            print(f"[normalize] Fixed single-quoted body (pattern A): {query[:200]}...")

        # Pattern B: cypher('MATCH...') — body as 1st arg (no graph name)
        elif not m_quoted_body:
            m_bad_wrap = re.search(
                r"(?:ag_catalog\.)?cypher\s*\(\s*'((?:MATCH|WITH|UNWIND)\b.*?)'(?:\s*,\s*[^)]+)?\s*\)\s*(?:AS\s*\([^)]*\)\s*)?;?\s*$",
                query, re.IGNORECASE | re.DOTALL
            )
            if m_bad_wrap and graph_name:
                cypher_body = m_bad_wrap.group(1).replace("''", "'")
                ret_match = re.search(r'RETURN\s+(.*?)$', cypher_body, re.IGNORECASE | re.DOTALL)
                if ret_match:
                    aliases = re.findall(r'\bAS\s+(\w+)', ret_match.group(1).strip().rstrip(';'), re.IGNORECASE)
                    if not aliases:
                        aliases = ["result"]
                    as_cols = ", ".join(f"{a} ag_catalog.agtype" for a in aliases)
                else:
                    as_cols = "result ag_catalog.agtype"
                query = f"SELECT * FROM ag_catalog.cypher('{graph_name}', $${cypher_body}$$) AS ({as_cols});"
                print(f"[normalize] Fixed missing $$ wrapper (pattern B): {query[:200]}...")

        # 1. Ensure ag_catalog.cypher() prefix
        #    Also fix: graph_name.cypher('...') → ag_catalog.cypher('graph_name', $$...$$)
        query = re.sub(r'\b\w+\.cypher\s*\(', 'ag_catalog.cypher(', query, flags=re.IGNORECASE)
        pattern = r'\b(FROM|JOIN)\s+cypher\s*\('
        replacement = r'\1 ag_catalog.cypher('
        query = re.sub(pattern, replacement, query, flags=re.IGNORECASE)

        # 2. Remove DATE keyword before string literals inside Cypher body
        #    e.g., DATE '2022-01-01' → '2022-01-01'
        query = re.sub(r'\bDATE\s+(\'[^\']+\')', r'\1', query, flags=re.IGNORECASE)

        # 3. Remove date() function calls — date('2022-01-01') → '2022-01-01'
        query = re.sub(r'\bdate\s*\(\s*(\'[^\']+\')\s*\)', r'\1', query, flags=re.IGNORECASE)

        # 4. Remove type casts like ::date, ::text, ::integer, ::bigint
        query = re.sub(r'::(date|text|integer|bigint|int|varchar|numeric)\b', '', query, flags=re.IGNORECASE)

        # 5. Fix column types in AS (...) clause — replace int/bigint/text/integer/agtype with ag_catalog.agtype
        #    Also fix: AS t(col1 text) → AS (col1 ag_catalog.agtype)
        #    Also fix: AS (col1 json, col2 jsonb) → AS (col1 ag_catalog.agtype, col2 ag_catalog.agtype)
        def fix_as_clause(m: re.Match) -> str:
            as_block = m.group(0)
            # Remove alias name: AS t(... → AS (...
            as_block = re.sub(r'\bAS\s+\w+\s*\(', 'AS (', as_block, flags=re.IGNORECASE)
            # Replace all non-agtype type names with ag_catalog.agtype
            as_block = re.sub(
                r'\b(bigint|int|integer|text|varchar|boolean|float|numeric|json|jsonb|agtype)\b',
                'ag_catalog.agtype',
                as_block,
                flags=re.IGNORECASE
            )
            # Deduplicate: ag_catalog.ag_catalog.agtype → ag_catalog.agtype
            as_block = as_block.replace('ag_catalog.ag_catalog.agtype', 'ag_catalog.agtype')
            return as_block

        # Find AS ... (...) after $$) — handle both AS (...) and AS alias(...)
        query = re.sub(r'\bAS\s+\w*\s*\([^)]+\)', fix_as_clause, query)

        # 5b. Fix column count mismatch — count RETURN aliases vs AS columns
        #     If they don't match, rebuild AS clause from RETURN
        dollar_parts = query.split('$$')
        if len(dollar_parts) >= 3:
            cypher_body = dollar_parts[1]
            ret_m = re.search(r'RETURN\s+(.*?)$', cypher_body, re.IGNORECASE | re.DOTALL)
            as_m = re.search(r'AS\s*\(([^)]+)\)\s*;?\s*$', query, re.IGNORECASE)
            if ret_m and as_m:
                # Count RETURN columns (split by comma, but respect function calls)
                ret_text = ret_m.group(1).strip().rstrip(';')
                # Simple split: count top-level commas (not inside parens)
                depth = 0
                ret_col_count = 1
                for ch in ret_text:
                    if ch == '(':
                        depth += 1
                    elif ch == ')':
                        depth -= 1
                    elif ch == ',' and depth == 0:
                        ret_col_count += 1

                as_text = as_m.group(1).strip()
                as_col_count = len(as_text.split(','))

                if ret_col_count != as_col_count:
                    # Rebuild AS clause from RETURN aliases
                    aliases = re.findall(r'\bAS\s+(\w+)', ret_text, re.IGNORECASE)
                    if not aliases or len(aliases) != ret_col_count:
                        aliases = [f"col{i+1}" for i in range(ret_col_count)]
                    new_as = ", ".join(f"{a} ag_catalog.agtype" for a in aliases)
                    query = re.sub(r'AS\s*\([^)]+\)\s*;?\s*$', f'AS ({new_as});', query, flags=re.IGNORECASE)
                    print(f"[normalize] Fixed AS column count: {as_col_count} → {ret_col_count}")

        # 6. Fix outer SELECT — ensure it's SELECT * FROM ag_catalog.cypher
        #    e.g., SELECT cnt FROM → SELECT * FROM
        #    Only apply if the query has ag_catalog.cypher
        if 'ag_catalog.cypher' in query.lower():
            query = re.sub(
                r'^\s*SELECT\s+(?!\*\s+FROM)[^*].*?\s+FROM\s+ag_catalog\.cypher',
                'SELECT * FROM ag_catalog.cypher',
                query,
                count=1,
                flags=re.IGNORECASE | re.DOTALL
            )

        # 7. Strip // and -- comments from inside Cypher body (between $$ delimiters)
        dollar_parts = query.split('$$')
        if len(dollar_parts) >= 3:
            cypher_body = dollar_parts[1]
            # Remove // comments
            cypher_body = re.sub(r'//[^\n]*', '', cypher_body)
            # Remove -- comments
            cypher_body = re.sub(r'--[^\n]*', '', cypher_body)
            # Remove /* */ block comments
            cypher_body = re.sub(r'/\*.*?\*/', '', cypher_body, flags=re.DOTALL)
            # Remove trailing semicolons inside Cypher body
            cypher_body = re.sub(r';\s*$', '', cypher_body.rstrip())

            # 7b. Fix IN ('a','b') → IN ['a','b'] (Cypher uses square brackets)
            def fix_in_parens(m: re.Match) -> str:
                return f"IN [{m.group(1)}]"
            cypher_body = re.sub(
                r"\bIN\s*\(\s*('[^)]*')\s*\)",
                fix_in_parens,
                cypher_body,
                flags=re.IGNORECASE
            )

            dollar_parts[1] = cypher_body
            query = '$$'.join(dollar_parts)

        # 8. Replace ILIKE with CONTAINS-based pattern inside Cypher body
        #    p.name ILIKE '%text%' → toLower(coalesce(p.name, '')) CONTAINS toLower('text')
        dollar_parts = query.split('$$')
        if len(dollar_parts) >= 3:
            cypher_body = dollar_parts[1]
            def ilike_to_contains(m: re.Match) -> str:
                prop = m.group(1).strip()
                text = m.group(2).strip().strip('%')
                return f"toLower(coalesce({prop}, '')) CONTAINS toLower('{text}')"
            cypher_body = re.sub(
                r'(\S+)\s+ILIKE\s+\'%([^%]+)%\'',
                ilike_to_contains,
                cypher_body,
                flags=re.IGNORECASE
            )

            # 8b. Fix WHERE var:Label → move label into MATCH
            #     Patterns: WHERE m:City_Council_Meeting AND ...
            #               WHERE (m:City_Council_Meeting OR m:Commission_Meeting)
            #     AGE doesn't support label checks in WHERE — they must be in MATCH
            #     Simple fix: remove label predicates from WHERE (they're redundant
            #     if the MATCH already constrains the label, or can't be fixed automatically)
            cypher_body = re.sub(
                r'\bWHERE\s+(\w+):(\w+)\s+AND\s+',
                r'WHERE ',
                cypher_body,
                flags=re.IGNORECASE
            )
            # Remove standalone WHERE var:Label at end
            cypher_body = re.sub(
                r'\bWHERE\s+(\w+):(\w+)\s*$',
                '',
                cypher_body,
                flags=re.IGNORECASE | re.MULTILINE
            )
            # Remove (m:Label OR m:Label) AND patterns
            cypher_body = re.sub(
                r'\bWHERE\s+\([^)]*:\w+[^)]*\)\s+AND\s+',
                'WHERE ',
                cypher_body,
                flags=re.IGNORECASE
            )
            # Remove AND (m:Label OR m:Label) mid-clause
            cypher_body = re.sub(
                r'\s+AND\s+\([^)]*:\w+[^)]*\)',
                '',
                cypher_body,
                flags=re.IGNORECASE
            )
            # Remove AND m:Label mid-clause
            cypher_body = re.sub(
                r'\s+AND\s+\w+:\w+\b',
                '',
                cypher_body,
                flags=re.IGNORECASE
            )

            # 8d. Fix missing payload. prefix on property access
            #     Common OSS error: c.id → c.payload.id, c.name → c.payload.name
            #     Only fix if NOT already preceded by "payload."
            cypher_body = re.sub(
                r'(?<!payload\.)(?<!payload\.attributes\.)\b(\w+)\.id\b(?!entifier)',
                r'\1.payload.id',
                cypher_body
            )
            cypher_body = re.sub(
                r'(?<!payload\.)(?<!payload\.attributes\.)\b(\w+)\.name\b',
                r'\1.payload.name',
                cypher_body
            )
            # Avoid double-fixing: payload.payload.id → payload.id
            cypher_body = cypher_body.replace('.payload.payload.', '.payload.')

            dollar_parts[1] = cypher_body
            query = '$$'.join(dollar_parts)

        return query

    @staticmethod
    def _apply_graph_name(query: str, graph_name: str | None) -> str:
        if not graph_name:
            return query
        pattern = r"ag_catalog\.cypher\s*\(\s*'[^']*'\s*,"
        replacement = f"ag_catalog.cypher('{graph_name}',"
        return re.sub(pattern, replacement, query, flags=re.IGNORECASE)

    async def query_using_sql_cypher(self, query: str, graph_name: str | None = None) -> list[dict]:
        query = self._normalize_cypher_query(query, graph_name)
        query = self._apply_graph_name(query, graph_name)
        print("Executing query:\n", query)

        max_retries = 2
        for attempt in range(max_retries):
            try:
                # Ensure connection is alive before executing
                await self._ensure_connected()
                
                async with self._conn.cursor() as cur:
                    # Ensure search path includes ag_catalog
                    await cur.execute('SET search_path = ag_catalog, "$user", public;')
                    await cur.execute(query)
                    rows = await cur.fetchall()
                    print("Raw rows:", rows)
                    return rows
            except psycopg.OperationalError as e:
                logger.error(f"Connection error on attempt {attempt + 1}/{max_retries}: {e}")
                logger.error(f"Failed query: {query[:300]}...")
                if attempt < max_retries - 1:
                    logger.info("Attempting to reconnect and retry...")
                    try:
                        await self._reconnect()
                    except Exception as reconnect_error:
                        logger.error(f"Reconnection failed: {reconnect_error}")
                        raise
                else:
                    logger.error("Max retries reached, giving up.")
                    raise
            except Exception as e:
                logger.error(f"Error executing query: {e}")
                logger.error(f"Failed query: {query[:500]}")
                try:
                    logger.info("Attempting to rollback transaction...")
                    await self._conn.rollback()
                    logger.info("Rollback successful.")
                except Exception:
                    pass
                raise

   

#if __name__ == "__main__":
#    asyncio.run(main())
