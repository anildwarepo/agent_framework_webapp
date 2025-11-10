import os, asyncio, json, re
import psycopg
from psycopg import sql
from dotenv import load_dotenv

load_dotenv()
DSN = dict(
    host=os.getenv("PGHOST", "localhost"),
    port=int(os.getenv("PGPORT", "5432")),
    dbname=os.getenv("PGDATABASE", "postgres"),
    user=os.getenv("PGUSER", "postgres"),
    password=os.getenv("PGPASSWORD", "postgres"),
)

GRAPH = "age_smoke"


def _validate_label(lbl: str):
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", lbl or ""):
        raise ValueError(f"Invalid label: {lbl!r}")


class PGAgeHelper:
    def __init__(self, conn: psycopg.AsyncConnection, graph: str):
        self._conn = conn
        self.graph = graph

    @classmethod
    async def create(cls, dsn: dict, graph: str):
        conn = await psycopg.AsyncConnection.connect(**dsn)
        async with conn.cursor() as cur:
            await cur.execute("SELECT 1 FROM pg_extension WHERE extname='age';")
            if not await cur.fetchone():
                await conn.close()
                raise RuntimeError(
                    "AGE extension is not installed in this database. "
                    "Run as superuser: CREATE EXTENSION age;"
                )
            await cur.execute('SET search_path = ag_catalog, "$user", public;')
        return cls(conn, graph)

    async def close(self):
        await self._conn.close()

    async def recreate_graph(self):
        async with self._conn.cursor() as cur:
            await cur.execute("SELECT 1 FROM ag_catalog.ag_graph WHERE name=%s;", (self.graph,))
            if await cur.fetchone():
                await cur.execute("SELECT ag_catalog.drop_graph(%s, true);", (self.graph,))
            await cur.execute("SELECT ag_catalog.create_graph(%s::name);", (self.graph,))
        await self._conn.commit()

    async def insert_node(self, payload_any: dict, node_label: str = "TestNode"):
        _validate_label(node_label)

        cypher_text = f"""
            CREATE (n:{node_label})
            SET n.payload = $payload
            RETURN n
        """

        q = sql.SQL("""
            SELECT *
            FROM ag_catalog.cypher({}::name, $cypher$
            {cypher}
            $cypher$, %s::ag_catalog.agtype) AS (n ag_catalog.agtype);
        """.replace("{cypher}", cypher_text)).format(sql.Literal(self.graph))

        params_obj = {"payload": payload_any}

        async with self._conn.cursor() as cur:
            await cur.execute(q, (json.dumps(params_obj),))
            row = await cur.fetchone()
        await self._conn.commit()
        return row[0]

    async def create_edge_by_ids(
        self,
        src_label: str,
        dst_label: str,
        edge_label: str,
        src_id,
        dst_id,
        edge_payload: dict | None = None,
    ):
        """
        Create (s)-[e:edge_label]->(t) where s.payload.id = src_id and t.payload.id = dst_id.
        Returns the created edge as ag_catalog.agtype (text form).
        """
        _validate_label(src_label)
        _validate_label(dst_label)
        _validate_label(edge_label)

        cypher_text = f"""
            MATCH (s:{src_label}), (t:{dst_label})
            WHERE s.payload.id = $src_id AND t.payload.id = $dst_id
            CREATE (s)-[e:{edge_label}]->(t)
            SET e.payload = $payload
            RETURN e
        """

        q = sql.SQL("""
            SELECT *
            FROM ag_catalog.cypher({}::name, $cypher$
            {cypher}
            $cypher$, %s::ag_catalog.agtype) AS (e ag_catalog.agtype);
        """.replace("{cypher}", cypher_text)).format(sql.Literal(self.graph))

        params_obj = {"src_id": src_id, "dst_id": dst_id, "payload": edge_payload or {}}

        async with self._conn.cursor() as cur:
            await cur.execute(q, (json.dumps(params_obj),))
            row = await cur.fetchone()

        await self._conn.commit()
        if not row:
            raise LookupError(
                f"No edge created. Check that nodes with payload.id={src_id!r} and {dst_id!r} exist."
            )
        return row[0]

    async def query_by_types(
        self,
        *,
        direction: str = "out",           # "out" | "in" | "both"
        src_label: str | None = None,     # match any if None
        edge_label: str | None = None,    # match any if None
        dst_label: str | None = None,     # match any if None
        src_id: str | None = None,        # filter s.payload.id if provided
        dst_id: str | None = None,        # filter t.payload.id if provided
        return_edges: bool = False,
        limit: int | None = None,
    ):
        """
        Find related nodes by node/edge *types* (labels), optionally filtering by src/dst payload.id.

        Returns rows as:
          - [(t,)] when return_edges=False
          - [(t, e)] when return_edges=True
        Each value is ag_catalog.agtype (text).
        """
        # 1) Validate identifiers
        _validate_label(src_label)
        _validate_label(edge_label)
        _validate_label(dst_label)

        # 2) Build pattern bits
        # direction
        rel_dir = {"out": "->", "in": "<-", "both": "-"}.get(direction)
        if rel_dir is None:
            raise ValueError("direction must be 'out', 'in', or 'both'")

        # labels
        src = f":{src_label}" if src_label else ""
        dst = f":{dst_label}" if dst_label else ""
        rel = f":{edge_label}" if edge_label else ""

        # 3) Build WHERE filters (no braces in text)
        where_clauses = ["TRUE"]
        if src_id is not None:
            where_clauses.append("s.payload.id = $src_id")
        if dst_id is not None:
            where_clauses.append("t.payload.id = $dst_id")
        where_sql = " AND ".join(where_clauses)

        # 4) SELECT/RETURN shape
        if return_edges:
            select_alias = "t ag_catalog.agtype, e ag_catalog.agtype"
            return_clause = "RETURN t, e"
        else:
            select_alias = "t ag_catalog.agtype"
            return_clause = "RETURN t"

        # 5) Optional LIMIT
        limit_clause = f"LIMIT {int(limit)}" if isinstance(limit, int) and limit > 0 else ""

        # 6) Cypher text (avoid {} to keep psycopg SQL.format happy)
        cypher_text = f"""
            MATCH (s{src}), (t{dst})
            MATCH (s)-[e{rel}]{rel_dir}(t)
            WHERE {where_sql}
            {return_clause}
            {limit_clause}
        """

        # 7) Compose SQL: graph literal, params as single agtype
        q = sql.SQL("""
            SELECT *
            FROM ag_catalog.cypher({}::name, $cypher$
            {cypher}
            $cypher$, %s::ag_catalog.agtype) AS ({select_alias});
        """.replace("{cypher}", cypher_text).replace("{select_alias}", select_alias)).format(
            sql.Literal(self.graph)
        )

        params_obj = {"src_id": src_id, "dst_id": dst_id}

        async with self._conn.cursor() as cur:
            await cur.execute(q, (json.dumps(params_obj),))
            rows = await cur.fetchall()
        return rows


    async def query_using_sql_cypher(self, query: str):
        """
        Execute an arbitrary Cypher-in-SQL statement safely.
        Rolls back after errors to clear aborted transaction state.
        """
        print("Executing query:\n", query)
        try:
            async with self._conn.cursor() as cur:
                await cur.execute(query)
                rows = await cur.fetchall()
                # If this function is read-only, no explicit commit is needed.
                # But if you sometimes run write queries, you could optionally:
                # await self._conn.commit()
                print(rows)
                return rows
        except Exception as e:
            # Important: clear the aborted state so the connection is usable again
            try:
                await self._conn.rollback()
            except Exception:
                # If rollback itself failed, you may need to reconnect upstream
                pass
            # Re-raise so callers see the error details
            raise



    # Convenience wrappers
    async def query_out_by_types(
        self,
        src_label: str | None = None,
        edge_label: str | None = None,
        dst_label: str | None = None,
        *,
        src_id: str | None = None,
        return_edges: bool = False,
        limit: int | None = None,
    ):
        return await self.query_by_types(
            direction="out",
            src_label=src_label,
            edge_label=edge_label,
            dst_label=dst_label,
            src_id=src_id,
            dst_id=None,
            return_edges=return_edges,
            limit=limit,
        )

    async def query_in_by_types(
        self,
        dst_label: str | None = None,
        edge_label: str | None = None,
        src_label: str | None = None,
        *,
        dst_id: str | None = None,
        return_edges: bool = False,
        limit: int | None = None,
    ):
        return await self.query_by_types(
            direction="in",
            src_label=dst_label,    # focal node plays "s" role in the helper
            edge_label=edge_label,
            dst_label=src_label,
            src_id=dst_id,
            dst_id=None,
            return_edges=return_edges,
            limit=limit,
        )

    async def query_both_by_types(
        self,
        node_label: str | None = None,
        edge_label: str | None = None,
        neighbor_label: str | None = None,
        *,
        node_id: str | None = None,
        return_edges: bool = False,
        limit: int | None = None,
    ):
        return await self.query_by_types(
            direction="both",
            src_label=node_label,
            edge_label=edge_label,
            dst_label=neighbor_label,
            src_id=node_id,
            dst_id=None,
            return_edges=return_edges,
            limit=limit,
        )

    async def health_check(self) -> bool:
        try:
            async with self._conn.cursor() as cur:
                await cur.execute("SELECT 1;")
                row = await cur.fetchone()
            return row is not None and row[0] == 1
        except Exception:
            
            return False

# ---- demo ----
async def main():
    helper = await PGAgeHelper.create(DSN, GRAPH)

    # Optional: fresh graph
    # await helper.recreate_graph()

    # Create two nodes that have payload.id set
    a = await helper.insert_node({"id": "A", "name": "Alpha"}, node_label="CustomNode")
    b = await helper.insert_node({"id": "B", "name": "Beta"}, node_label="CustomNode")
    print("Created nodes:\n ", a, "\n ", b)

    # Create an edge between them
    e = await helper.create_edge_by_ids(
        src_label="CustomNode",
        dst_label="CustomNode",
        edge_label="CONNECTS",
        src_id="A",
        dst_id="B",
        edge_payload={"weight": 0.75},
    )
    print("Created edge:", e)


    # 1) All CustomNode --CONNECTS--> CustomNode targets (any source), just nodes:
    rows = await helper.query_out_by_types(
        src_label="CustomNode",
        edge_label="CONNECTS",
        dst_label="CustomNode",
        return_edges=False,
        limit=50,
    )
    targets = [r[0] for r in rows]
    print("Targets:", targets)

    # 2) All edges of type CONNECTS from a specific source node (identified by payload.id):
    rows = await helper.query_out_by_types(
        src_label="CustomNode",
        edge_label="CONNECTS",
        dst_label=None,          # any destination label
        src_id="A",              # filter by source node payload.id
        return_edges=True,       # include edge
        limit=25,
    )
    for t, e in rows:
        print("To:", t)
        print("Edge:", e)

    # 3) Undirected neighbors by *types* (both directions), optional node_id:
    rows = await helper.query_both_by_types(
        node_label="Person",
        edge_label="KNOWS",
        neighbor_label="Person",
        node_id=None,           # if provided, restrict focal node by payload.id
        return_edges=False,
        limit=100,
    )
    print("Neighbors:", [r[0] for r in rows])

    await helper.close()


#if __name__ == "__main__":
#    asyncio.run(main())
