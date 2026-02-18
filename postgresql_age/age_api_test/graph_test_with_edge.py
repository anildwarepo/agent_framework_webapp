#!/usr/bin/env python3
import os
import psycopg2

DSN = dict(
    host=os.getenv("PGHOST", "localhost"),
    port=int(os.getenv("PGPORT", "5432")),
    dbname=os.getenv("PGDATABASE", "postgres"),
    user=os.getenv("PGUSER", "postgres"),
    password=os.getenv("PGPASSWORD", "postgres"),
)

GRAPH = "age_smoke_2"

def ensure_age_ready(cur):
    # Must have been run once by a superuser in THIS database:
    #   CREATE EXTENSION age;
    cur.execute("SELECT 1 FROM pg_extension WHERE extname='age';")
    if not cur.fetchone():
        raise RuntimeError(
            "AGE extension is not installed in this database. "
            "Run: CREATE EXTENSION age; (as superuser)"
        )
    # Put AGE schema first for this session (doesn't require superuser)
    cur.execute('SET search_path = ag_catalog, "$user", public;')

def recreate_graph(cur, name: str):
    # Drop if it exists
    cur.execute("SELECT 1 FROM ag_catalog.ag_graph WHERE name=%s;", (name,))
    if cur.fetchone():
        cur.execute("SELECT ag_catalog.drop_graph(%s, true);", (name,))
    # Create fresh
    cur.execute("SELECT ag_catalog.create_graph(%s::name);", (name,))

with psycopg2.connect(**DSN) as conn:
    conn.autocommit = True
    with conn.cursor() as cur:
        ensure_age_ready(cur)
        recreate_graph(cur, GRAPH)

        # Create a single node
        cur.execute("""
            SELECT *
            FROM ag_catalog.cypher(%s, $$
                CREATE (n:TestNode {name:'hello', nps:42})
                RETURN n
            $$) AS (n ag_catalog.agtype);
        """, (GRAPH,))
        print("Created node:", cur.fetchone()[0])

        # Read it back
        cur.execute("""
            SELECT *
            FROM ag_catalog.cypher(%s, $$ MATCH (n:TestNode) RETURN n $$)
            AS (n ag_catalog.agtype);
        """, (GRAPH,))
        rows = cur.fetchall()
        print("Readback:", [r[0] for r in rows])

        # Count nodes
        cur.execute("""
            SELECT *
            FROM ag_catalog.cypher(%s, $$ MATCH (n:TestNode) RETURN count(n) $$)
            AS (cnt ag_catalog.agtype);
        """, (GRAPH,))
        print("Count:", cur.fetchone()[0])
