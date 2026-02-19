#!/usr/bin/env python3
import os
import re
import json
import asyncio
import selectors
import time
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
    sslmode=os.getenv("PGSSLMODE", "require"),
)

GRAPH = os.getenv("GRAPH_NAME", "age_smoke_2")
DATA_DIR = os.getenv("DATA_DIR", "../data")
NODES_FILE = os.getenv("NODES_FILE", os.path.join(DATA_DIR, "graph_nodes.json"))
EDGES_FILE = os.getenv("EDGES_FILE", os.path.join(DATA_DIR, "graph_edges.json"))


print(f"Using DSN: host={DSN['host']} port={DSN['port']} dbname={DSN['dbname']} user={DSN['user']}")
print(f"Using graph: {GRAPH}")

# -----------------------------
# Utilities
# -----------------------------
_LABEL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")

def _validate_label(label: str):
    if not _LABEL_RE.match(label or ""):
        raise ValueError(f"Invalid label: {label!r}")

def _read_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# -----------------------------
# AGE Helper (async psycopg)
# -----------------------------
class PGAgeHelper:
    def __init__(self, conn: psycopg.AsyncConnection, graph: str):
        self._conn = conn
        self.graph = graph

    @classmethod
    async def create(cls, dsn: dict, graph: str):
        conn = await psycopg.AsyncConnection.connect(**dsn)
        self = cls(conn, graph)
        async with conn.cursor() as cur:
            # Ensure AGE extension present
            await cur.execute("CREATE EXTENSION IF NOT EXISTS AGE CASCADE;")
            # Put ag_catalog on search_path for this session
            await cur.execute('SET search_path = ag_catalog, "$user", public;')
            
            # Always drop and recreate the graph
            # First check if graph exists in ag_graph
            await cur.execute("SELECT graphid FROM ag_catalog.ag_graph WHERE name=%s;", (graph,))
            row = await cur.fetchone()
            if row:
                graph_oid = row[0]
                # Delete labels for this graph (foreign key to ag_graph)
                await cur.execute("DELETE FROM ag_catalog.ag_label WHERE graph=%s;", (graph_oid,))
                # Delete the graph entry
                await cur.execute("DELETE FROM ag_catalog.ag_graph WHERE name=%s;", (graph,))
            
            # Drop schema if exists (handles orphaned schemas too)
            await cur.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE;").format(sql.Identifier(graph)))
            await conn.commit()
            
            # Create fresh graph
            await cur.execute("SELECT ag_catalog.create_graph(%s::name);", (graph,))
            print("Created graph:", graph)
        await conn.commit()
        return self

    async def create_index_on_payload_id(self, label: str):
        """Create a btree index on payload.id for faster edge lookups."""
        _validate_label(label)
        index_name = f"idx_{self.graph}_{label}_payload_id"
        # AGE stores vertex properties in 'properties' column as agtype
        # Cast agtype to text, then to jsonb, then extract payload.id
        index_sql = sql.SQL("""
            CREATE INDEX IF NOT EXISTS {idx_name} 
            ON {table} (((properties::text)::jsonb->'payload'->>'id'));
        """).format(
            idx_name=sql.Identifier(index_name),
            table=sql.Identifier(self.graph, label)
        )
        async with self._conn.cursor() as cur:
            await cur.execute(index_sql)
        await self._conn.commit()
        print(f"Created index on {label}.payload.id")

    async def close(self):
        await self._conn.close()

    # ---------- Single node ----------
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

    # ---------- Single edge by payload.id (optimized: no cartesian product) ----------
    async def create_edge_by_ids(
        self,
        src_label: str,
        dst_label: str,
        edge_label: str,
        src_id,
        dst_id,
        edge_payload: dict | None = None,
    ):
        _validate_label(src_label)
        _validate_label(dst_label)
        _validate_label(edge_label)

        # IMPORTANT: split MATCH to avoid cartesian product of all s,t
        cypher_text = f"""
            MATCH (s:{src_label})
            WHERE s.payload.id = $src_id
            MATCH (t:{dst_label})
            WHERE t.payload.id = $dst_id
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

    # ---------- Batched nodes using direct SQL INSERT (fastest - bypasses Cypher) ----------
    async def batch_insert_nodes(self, label: str, payload_rows: list[dict], chunk_size: int = 10000) -> dict[str, str]:
        """
        payload_rows: list of dicts, each MUST contain 'id' (used later by edges).
        chunk_size: process nodes in chunks
        Returns: dict mapping payload id -> AGE vertex id (as text for graphid casting)
        """
        if not payload_rows:
            return {}
        _validate_label(label)

        total_count = len(payload_rows)
        print(f"Batch inserting {total_count} nodes with label {label}")
        start_time = time.time()
        
        # First, create the vertex label via Cypher (creates the table)
        async with self._conn.cursor() as cur:
            await cur.execute("""
                SELECT 1 FROM ag_catalog.ag_label 
                WHERE name = %s AND graph = (SELECT graphid FROM ag_catalog.ag_graph WHERE name = %s);
            """, (label, self.graph))
            if not await cur.fetchone():
                # Create label by inserting one node via Cypher
                cypher_create = f"CREATE (n:{label}) SET n.payload = $p RETURN id(n)"
                q_create = sql.SQL("""
                    SELECT * FROM ag_catalog.cypher({}::name, $cypher$
                    {cypher}
                    $cypher$, %s::ag_catalog.agtype) AS (vid ag_catalog.agtype);
                """.replace("{cypher}", cypher_create)).format(sql.Literal(self.graph))
                await cur.execute(q_create, (json.dumps({"p": payload_rows[0]}),))
                await self._conn.commit()
                payload_rows = payload_rows[1:]
                total_count -= 1
        
        if total_count == 0:
            # Only had one node, query and return
            return await self._query_vertex_ids(label, start_time)

        # Get graph oid and sequence name for constructing vertex IDs
        async with self._conn.cursor() as cur:
            await cur.execute("""
                SELECT l.graph, l.id, l.seq_name FROM ag_catalog.ag_label l
                JOIN ag_catalog.ag_graph g ON l.graph = g.graphid
                WHERE l.name = %s AND g.name = %s;
            """, (label, self.graph))
            row = await cur.fetchone()
            graph_oid = row[0]
            label_id = row[1]
            seq_name_raw = row[2]  # AGE stores just the sequence name without schema
            # Fully qualify the sequence name with schema
            seq_name = f'"{self.graph}"."{seq_name_raw}"'
        
        # Direct SQL INSERT into vertex table - let AGE handle ID generation via DEFAULT
        vertex_table = sql.Identifier(self.graph, label)
        
        total_inserted = 0
        num_chunks = (total_count + chunk_size - 1) // chunk_size
        
        for i in range(0, total_count, chunk_size):
            chunk = payload_rows[i:i + chunk_size]
            chunk_num = i // chunk_size + 1
            
            # Build VALUES for batch insert - only insert properties, let id use DEFAULT
            values_list = []
            params = []
            for payload in chunk:
                values_list.append(sql.SQL("(%s::ag_catalog.agtype)"))
                params.append(json.dumps({"payload": payload}))
            
            insert_sql = sql.SQL("INSERT INTO {} (properties) VALUES ").format(vertex_table) + sql.SQL(", ").join(values_list)
            
            async with self._conn.cursor() as cur:
                await cur.execute(insert_sql, params)
                total_inserted += len(chunk)
            await self._conn.commit()
            
            if num_chunks > 1:
                elapsed = time.time() - start_time
                print(f"  Chunk {chunk_num}/{num_chunks}: {len(chunk)} nodes ({elapsed:.2f}s elapsed)")
        
        elapsed = time.time() - start_time
        print(f"Inserted {total_inserted + 1} nodes with label {label} in {elapsed:.2f}s")
        
        return await self._query_vertex_ids(label, start_time)
    
    async def _query_vertex_ids(self, label: str, start_time: float) -> dict[str, int]:
        """Query vertex IDs from the table directly."""
        print(f"  Querying vertex IDs for {label}...")
        query_start = time.time()
        vertex_table = sql.Identifier(self.graph, label)
        # Keep id as-is (don't convert to int) - we need the raw graphid value
        id_query = sql.SQL("""
            SELECT id::text, (properties::text)::jsonb->'payload'->>'id' AS pid
            FROM {}
        """).format(vertex_table)
        
        id_map: dict[str, str] = {}  # payload_id -> graphid as text
        async with self._conn.cursor() as cur:
            await cur.execute(id_query)
            async for row in cur:
                vid = row[0]  # Keep as text representation of graphid
                pid = row[1]
                if pid:
                    id_map[pid] = vid
        
        print(f"  Got {len(id_map)} vertex IDs in {time.time() - query_start:.2f}s")
        return id_map

    # ---------- Batched edges using direct SQL INSERT (fastest - bypasses Cypher) ----------
    async def batch_create_edges_direct(self, edge_label: str, edge_rows: list[dict], chunk_size: int = 10000):
        """
        edge_rows: list of {"src_vid": AGE vertex id, "dst_vid": AGE vertex id, "payload": {...}}
        Uses direct SQL INSERT into AGE's edge tables - bypasses slow Cypher MATCH.
        """
        if not edge_rows:
            return 0
        _validate_label(edge_label)
        
        total_count = len(edge_rows)
        print(f"Batch inserting {total_count} edges with label {edge_label}")
        start_time = time.time()
        
        # First ensure edge label exists by creating one edge via Cypher
        # This creates the edge table with proper structure
        async with self._conn.cursor() as cur:
            # Get graph oid, label id, and sequence name
            await cur.execute("""
                SELECT l.graph, l.id, l.seq_name FROM ag_catalog.ag_label l
                JOIN ag_catalog.ag_graph g ON l.graph = g.graphid 
                WHERE l.name = %s AND g.name = %s;
            """, (edge_label, self.graph))
            label_row = await cur.fetchone()
            
            if not label_row:
                # Create the edge label by inserting one edge via Cypher
                first = edge_rows[0]
                cypher_create_label = f"""
                    MATCH (s) WHERE id(s) = $src
                    MATCH (t) WHERE id(t) = $dst
                    CREATE (s)-[e:{edge_label}]->(t)
                    SET e.payload = $payload
                    RETURN id(e)
                """
                q_create = sql.SQL("""
                    SELECT * FROM ag_catalog.cypher({}::name, $cypher$
                    {cypher}
                    $cypher$, %s::ag_catalog.agtype) AS (eid ag_catalog.agtype);
                """.replace("{cypher}", cypher_create_label)).format(sql.Literal(self.graph))
                await cur.execute(q_create, (json.dumps({"src": first["src_vid"], "dst": first["dst_vid"], "payload": first["payload"]}),))
                await self._conn.commit()
                
                # Now get the label info
                await cur.execute("""
                    SELECT l.graph, l.id, l.seq_name FROM ag_catalog.ag_label l
                    JOIN ag_catalog.ag_graph g ON l.graph = g.graphid 
                    WHERE l.name = %s AND g.name = %s;
                """, (edge_label, self.graph))
                label_row = await cur.fetchone()
                edge_rows = edge_rows[1:]  # Skip first since we already inserted it
                total_count -= 1
            
            graph_oid = label_row[0]
            label_id = label_row[1]
            seq_name_raw = label_row[2]
            # Fully qualify the sequence name with schema
            seq_name = f'"{self.graph}"."{seq_name_raw}"'
        await self._conn.commit()
        
        if total_count == 0:
            elapsed = time.time() - start_time
            print(f"Inserted 1 edges with label {edge_label} in {elapsed:.2f}s")
            return 1

        # Direct SQL INSERT into the edge table
        edge_table = sql.Identifier(self.graph, edge_label)
        
        total_inserted = 0
        num_chunks = (total_count + chunk_size - 1) // chunk_size
        
        for i in range(0, total_count, chunk_size):
            chunk = edge_rows[i:i + chunk_size]
            chunk_num = i // chunk_size + 1
            
            # Build VALUES for batch insert - graphid from text
            values_list = []
            params = []
            for edge in chunk:
                # Cast text back to graphid
                values_list.append(sql.SQL("(%s::ag_catalog.graphid, %s::ag_catalog.graphid, %s::ag_catalog.agtype)"))
                params.extend([edge["src_vid"], edge["dst_vid"], json.dumps({"payload": edge["payload"]})])
            
            insert_sql = sql.SQL("INSERT INTO {} (start_id, end_id, properties) VALUES ").format(edge_table) + sql.SQL(", ").join(values_list)
            
            async with self._conn.cursor() as cur:
                await cur.execute(insert_sql, params)
                total_inserted += len(chunk)
            await self._conn.commit()
            
            if num_chunks > 1:
                elapsed = time.time() - start_time
                print(f"  Chunk {chunk_num}/{num_chunks}: {len(chunk)} edges ({elapsed:.2f}s elapsed)")
        
        # Add 1 if we created the label edge
        if total_count < len(edge_rows) + 1:
            total_inserted += 1
            
        elapsed = time.time() - start_time
        print(f"Inserted {total_inserted} edges with label {edge_label} in {elapsed:.2f}s")
        return total_inserted

# -----------------------------
# Loader from graph_* files
# -----------------------------
async def load_from_files():
    total_start_time = time.time()
    nodes_raw = _read_json(NODES_FILE)
    edges_raw = _read_json(EDGES_FILE)

    # Normalize nodes by label -> payload list (payload has id + props)
    nodes_by_label: dict[str, list[dict]] = {}
    for n in nodes_raw:
        if n.get("kind") != "\"node\"":
            continue
        label = n["label"]
        _validate_label(label)
        nid = n["id"]
        props = n.get("properties") or "{}"
        try:
            props = json.loads(props)
        except Exception:
            props = {}
        payload = {"id": nid, **props, "label": label}
        nodes_by_label.setdefault(label, []).append(payload)

    # Build id -> label from nodes (for accurate typing in edge MATCH)
    id_to_label: dict[str, str] = {}
    for label, rows in nodes_by_label.items():
        for p in rows:
            id_to_label[str(p["id"])] = label

    # Normalize edges by (src_label, dst_label, edge_label) -> rows
    edges_by_triplet: dict[tuple[str, str, str], list[dict]] = {}
    skipped_missing = 0
    for e in edges_raw:
        if e.get("kind") != "\"edge\"":
            continue
        src_id = str(e["src"])
        dst_id = str(e["dst"])
        elabel = e["label"]
        _validate_label(elabel)

        src_label = id_to_label.get(src_id)
        dst_label = id_to_label.get(dst_id)
        if not src_label or not dst_label:
            skipped_missing += 1
            continue

        props = e.get("properties") or "{}"
        try:
            props = json.loads(props)
        except Exception:
            props = {}
        row = {"src_id": src_id, "dst_id": dst_id, "payload": props}
        edges_by_triplet.setdefault((src_label, dst_label, elabel), []).append(row)

    # Connect & load
    helper = await PGAgeHelper.create(DSN, GRAPH)
    try:
        # Insert nodes per label (batched) - collect vertex ID mappings
        total_nodes = 0
        id_to_vertex: dict[str, int] = {}  # payload.id -> AGE vertex id
        for label, payloads in nodes_by_label.items():
            label_map = await helper.batch_insert_nodes(label, payloads)
            id_to_vertex.update(label_map)
            total_nodes += len(label_map)

        print(f"\nBuilt vertex ID map with {len(id_to_vertex)} entries\n")

        # Convert edges to use vertex IDs (as text for graphid casting)
        edges_by_label: dict[str, list[dict]] = {}
        skipped_no_vertex = 0
        for (src_label, dst_label, edge_label), rows in edges_by_triplet.items():
            for row in rows:
                src_vid = id_to_vertex.get(row["src_id"])  # Returns graphid as text
                dst_vid = id_to_vertex.get(row["dst_id"])  # Returns graphid as text
                if src_vid is None or dst_vid is None:
                    skipped_no_vertex += 1
                    continue
                edges_by_label.setdefault(edge_label, []).append({
                    "src_vid": src_vid,
                    "dst_vid": dst_vid,
                    "payload": row["payload"]
                })

        # Insert edges per label using direct SQL (fast!)
        total_edges = 0
        for edge_label, rows in edges_by_label.items():
            total_edges += await helper.batch_create_edges_direct(edge_label, rows)

        print(f"Inserted nodes: {total_nodes}")
        print(f"Inserted edges: {total_edges}")
        if skipped_missing:
            print(f"Skipped edges with missing endpoints (label): {skipped_missing}")
        if skipped_no_vertex:
            print(f"Skipped edges with missing vertex IDs: {skipped_no_vertex}")
        total_elapsed = time.time() - total_start_time
        print(f"\nTotal processing time: {total_elapsed:.2f}s")
    finally:
        await helper.close()

# -----------------------------
# Entrypoint
# -----------------------------
if __name__ == "__main__":
    asyncio.run(load_from_files(), loop_factory=asyncio.SelectorEventLoop)
