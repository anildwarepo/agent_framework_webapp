#!/usr/bin/env python3
import os
import psycopg
from psycopg import sql
from psycopg.types.json import Json  # only needed if you pass params to cypher

DSN = dict(
    host=os.getenv("PGHOST", "localhost"),
    port=int(os.getenv("PGPORT", "5432")),
    dbname=os.getenv("PGDATABASE", "postgres"),
    user=os.getenv("PGUSER", "postgres"),
    password=os.getenv("PGPASSWORD", "postgres"),
)

GRAPH = "age_smoke"

def ensure_age_ready(cur: psycopg.Cursor) -> None:
    cur.execute("SELECT 1 FROM pg_extension WHERE extname='age';")
    if not cur.fetchone():
        raise RuntimeError(
            "AGE extension is not installed in this database. "
            "Run: CREATE EXTENSION age; (as superuser)"
        )
    cur.execute('SET search_path = ag_catalog, "$user", public;')

def recreate_graph(cur: psycopg.Cursor, name: str) -> None:
    # Here it's fine to pass as parameter for create/drop helpers
    cur.execute("SELECT 1 FROM ag_catalog.ag_graph WHERE name=%s;", (name,))
    if cur.fetchone():
        cur.execute("SELECT ag_catalog.drop_graph(%s, true);", (name,))
    cur.execute("SELECT ag_catalog.create_graph(%s::name);", (name,))

def cypher_literal_graph(graph_name: str) -> sql.Composed:
    """
    Build the 'graph name constant' required by AGE's cypher() as a safe literal.
    Produces: '<graph_name>'::name
    """
    return sql.SQL("{}::name").format(sql.Literal(graph_name))

if __name__ == "__main__":
    with psycopg.connect(**DSN) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            ensure_age_ready(cur)
            recreate_graph(cur, GRAPH)

            gconst = cypher_literal_graph(GRAPH)

            # Create a single node (no params arg)
            cur.execute(
                sql.SQL("""
                    SELECT *
                    FROM ag_catalog.cypher({g}, $cypher$
                        CREATE (n:TestNode {name:'hello', nps:42})
                        RETURN n
                    $cypher$) AS (n ag_catalog.agtype);
                """).format(g=gconst)
            )
            print("Created node:", cur.fetchone()[0])

            # Read it back (no params arg)
            cur.execute(
                sql.SQL("""
                    SELECT *
                    FROM ag_catalog.cypher({g}, $cypher$
                        MATCH (n:TestNode) RETURN n
                    $cypher$) AS (n ag_catalog.agtype);
                """).format(g=gconst)
            )
            rows = cur.fetchall()
            print("Readback:", [r[0] for r in rows])

            # Count nodes (no params arg)
            cur.execute(
                sql.SQL("""
                    SELECT *
                    FROM ag_catalog.cypher({g}, $cypher$
                        MATCH (n:TestNode) RETURN count(n)
                    $cypher$) AS (cnt ag_catalog.agtype);
                """).format(g=gconst)
            )
            print("Count:", cur.fetchone()[0])

            # Example WITH params (notice the third arg is a bind parameter!)
            cur.execute(
                sql.SQL("""
                    SELECT *
                    FROM ag_catalog.cypher({g}, $cypher$
                        MATCH (n:TestNode {name: $name})
                        RETURN n
                    $cypher$, %s) AS (n ag_catalog.agtype);
                """).format(g=gconst),
                (Json({"name": "hello"}),)  # third arg must be a parameter
            )
            print("Query with params:", cur.fetchone()[0])
