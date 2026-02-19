# pg_age_helper.py

import os, asyncio, json, re
import psycopg
from psycopg import sql
from psycopg.rows import dict_row   # 👈 NEW
from dotenv import load_dotenv
from typing import Any, List

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
            
            # Set search path for this session
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

        return cls(conn)

    @staticmethod
    def _normalize_cypher_query(query: str) -> str:
        """
        Ensure we always call ag_catalog.cypher(...) instead of bare cypher(...).
        """
        # Matches FROM cypher( or JOIN cypher( with optional whitespace
        pattern = r'\b(FROM|JOIN)\s+cypher\s*\('
        replacement = r'\1 ag_catalog.cypher('
        return re.sub(pattern, replacement, query, flags=re.IGNORECASE)

    async def query_using_sql_cypher(self, query: str) -> list[dict]:
        query = self._normalize_cypher_query(query)
        print("Executing query:\n", query)

        try:
            async with self._conn.cursor() as cur:
                # Ensure search path includes ag_catalog for AGE functions
                await cur.execute('SET search_path = ag_catalog, "$user", public;')
                await cur.execute(query)
                rows = await cur.fetchall()
                print("Raw rows:", rows)
                return rows
        except Exception as e:
            print("Error executing query:", e)
            try:
                print("Attempting to rollback transaction...")
                await self._conn.rollback()
                print("Rollback successful.")
            except Exception:
                # If rollback itself failed, you may need to reconnect upstream
                pass
            raise

   

#if __name__ == "__main__":
#    asyncio.run(main())
