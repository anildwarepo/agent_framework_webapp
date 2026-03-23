#!/usr/bin/env python3
import os
import re
import json
import time
import hashlib
import asyncio
import selectors
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
    connect_timeout=30,
)

GRAPH = os.getenv("GRAPH_NAME", os.getenv("GRAPH", "meetings_graph_v2"))
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "10000"))
PARALLEL_EDGES = int(os.getenv("PARALLEL_EDGES", "10"))

DATA_DIR = os.getenv("DATA_DIR", "../data")


GRAPH_DATA_FILE = os.getenv(
    "GRAPH_DATA_FILE",
    os.path.join(DATA_DIR, "meetings_graph_v2.json"),
)

_VALID_LABEL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_NON_LABEL_CHAR_RE = re.compile(r"[^A-Za-z0-9_]")


def _validate_label(label: str) -> None:
    if not _VALID_LABEL_RE.match(label or ""):
        raise ValueError(f"Invalid AGE label: {label!r}")


def _sanitize_label(raw: str | None, fallback: str) -> str:
    label = _NON_LABEL_CHAR_RE.sub("_", (raw or "").strip())
    label = re.sub(r"_+", "_", label).strip("_")
    if not label:
        label = fallback
    if not label[0].isalpha():
        label = f"{fallback}_{label}"
    label = label[:55]
    _validate_label(label)
    return label


def _unique_label(
    raw: str,
    fallback: str,
    used_labels: set[str],
    reserved_labels: set[str] | None = None,
    suffix_hint: str = "",
) -> str:
    reserved = reserved_labels or set()
    base = _sanitize_label(raw, fallback)
    candidate = base

    if candidate in reserved:
        candidate = _sanitize_label(f"{base}{suffix_hint}", fallback)

    if candidate not in used_labels and candidate not in reserved:
        used_labels.add(candidate)
        return candidate

    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
    suffix = f"_{digest}"
    max_base_len = max(1, 55 - len(suffix))
    trimmed = base[:max_base_len].rstrip("_") or fallback
    candidate = f"{trimmed}{suffix}"
    _validate_label(candidate)

    counter = 1
    while candidate in used_labels or candidate in reserved:
        counter_suffix = f"_{digest}{counter}"
        max_base_len = max(1, 55 - len(counter_suffix))
        trimmed = base[:max_base_len].rstrip("_") or fallback
        candidate = f"{trimmed}{counter_suffix}"
        _validate_label(candidate)
        counter += 1

    used_labels.add(candidate)
    return candidate


def _read_graph_json(path: str) -> dict:
    file_size = os.path.getsize(path)
    print(f"JSON file size: {file_size / (1024**3):.2f} GB ({file_size:,} bytes)")
    print("Parsing JSON (this may take a while for large files)...", flush=True)
    t0 = time.time()
    with open(path, "r", encoding="utf-8") as file:
        data = json.load(file)
    print(f"JSON parsed in {time.time() - t0:.1f}s", flush=True)
    return data


class PGAgeHelper:
    def __init__(self, conn: psycopg.AsyncConnection, graph: str):
        self._conn = conn
        self.graph = graph

    @classmethod
    async def create(cls, dsn: dict, graph: str):
        print("Connecting to database...", flush=True)
        t0 = time.time()
        conn = await psycopg.AsyncConnection.connect(**dsn)
        print(f"  Connected in {time.time() - t0:.1f}s", flush=True)

        async with conn.cursor() as cur:
            print("  Ensuring AGE extension exists...", flush=True)
            t0 = time.time()
            await cur.execute("CREATE EXTENSION IF NOT EXISTS AGE CASCADE;")
            print(f"  Extension ready in {time.time() - t0:.1f}s", flush=True)

            await cur.execute('SET search_path = ag_catalog, "$user", public;')
            await cur.execute(
                "SELECT 1 FROM ag_catalog.ag_graph WHERE name=%s;",
                (graph,),
            )
            existing = await cur.fetchone()
            if existing:
                # Terminate other sessions that may hold locks on graph tables
                print("  Terminating other sessions that may block drop_graph...", flush=True)
                await cur.execute("""
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE pid <> pg_backend_pid()
                      AND datname = current_database()
                      AND state <> 'idle'
                      AND query LIKE '%%' || %s || '%%';
                """, (graph,))
                # Also kill idle connections that might hold open transactions
                await cur.execute("""
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE pid <> pg_backend_pid()
                      AND datname = current_database()
                      AND state = 'idle in transaction';
                """)
                await conn.commit()
                # Small delay to let backends terminate
                await asyncio.sleep(1)

                print(f"  Dropping existing graph '{graph}' (this can take a while)...", flush=True)
                t0 = time.time()
                await cur.execute("SELECT ag_catalog.drop_graph(%s::name, true);", (graph,))
                print(f"  Graph dropped in {time.time() - t0:.1f}s", flush=True)
            else:
                print(f"  No existing graph '{graph}' to drop.", flush=True)
            await conn.commit()

        await conn.close()

        print(f"Creating graph '{graph}'...", flush=True)
        t0 = time.time()
        conn = await psycopg.AsyncConnection.connect(**dsn)
        async with conn.cursor() as cur:
            await cur.execute("CREATE EXTENSION IF NOT EXISTS AGE CASCADE;")
            await cur.execute('SET search_path = ag_catalog, "$user", public;')
            try:
                await cur.execute("SELECT ag_catalog.create_graph(%s::name);", (graph,))
            except psycopg.Error as exc:
                msg = str(exc).lower()
                if "cache corrupted" in msg:
                    print("  Cache corrupted, retrying graph creation...", flush=True)
                    await conn.rollback()
                    await conn.close()
                    conn = await psycopg.AsyncConnection.connect(**dsn)
                    async with conn.cursor() as retry_cur:
                        await retry_cur.execute("CREATE EXTENSION IF NOT EXISTS AGE CASCADE;")
                        await retry_cur.execute('SET search_path = ag_catalog, "$user", public;')
                        await retry_cur.execute("SELECT ag_catalog.create_graph(%s::name);", (graph,))
                else:
                    raise
            await conn.commit()
        print(f"Graph created in {time.time() - t0:.1f}s", flush=True)

        return cls(conn, graph)

    async def close(self):
        await self._conn.close()

    async def batch_insert_nodes(self, label: str, payload_rows: list[dict], chunk_size: int = 10000) -> dict[str, str]:
        if not payload_rows:
            return {}
        _validate_label(label)

        total_count = len(payload_rows)
        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                SELECT 1 FROM ag_catalog.ag_label l
                JOIN ag_catalog.ag_graph g ON l.graph = g.graphid
                WHERE l.name = %s AND g.name = %s;
                """,
                (label, self.graph),
            )
            if not await cur.fetchone():
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
            table = sql.Identifier(self.graph, label)
            return await self._query_vertex_ids(table)

        table = sql.Identifier(self.graph, label)
        num_chunks = (len(payload_rows) + chunk_size - 1) // chunk_size
        for chunk_idx, i in enumerate(range(0, len(payload_rows), chunk_size), 1):
            chunk = payload_rows[i:i + chunk_size]
            values = [sql.SQL("(%s::ag_catalog.agtype)") for _ in chunk]
            params = [json.dumps({"payload": row}) for row in chunk]
            insert_sql = sql.SQL("INSERT INTO {} (properties) VALUES ").format(table) + sql.SQL(", ").join(values)
            async with self._conn.cursor() as cur:
                await cur.execute(insert_sql, params)
            await self._conn.commit()
            done = min(i + chunk_size, len(payload_rows))
            print(f"  [{label}] nodes chunk {chunk_idx}/{num_chunks}  "
                  f"({done:,}/{len(payload_rows):,})", flush=True)

        print(f"  [{label}] querying vertex IDs...", flush=True)
        return await self._query_vertex_ids(table)

    async def _query_vertex_ids(self, table: sql.Identifier) -> dict[str, str]:
        id_query = sql.SQL("""
            SELECT id::text, (properties::text)::jsonb->'payload'->>'id' AS pid
            FROM {}
        """).format(table)

        out: dict[str, str] = {}
        async with self._conn.cursor() as cur:
            await cur.execute(id_query)
            async for row in cur:
                vertex_id, payload_id = row
                if payload_id:
                    out[str(payload_id)] = vertex_id
        return out

    async def batch_insert_edges(self, label: str, edge_rows: list[dict], chunk_size: int = 10000) -> int:
        if not edge_rows:
            return 0
        _validate_label(label)

        total_count = len(edge_rows)
        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                SELECT 1 FROM ag_catalog.ag_label l
                JOIN ag_catalog.ag_graph g ON l.graph = g.graphid
                WHERE l.name = %s AND g.name = %s;
                """,
                (label, self.graph),
            )
            if not await cur.fetchone():
                cypher_bootstrap = f"""
                    MATCH (s)
                    WITH s LIMIT 1
                    MATCH (t)
                    WITH s, t LIMIT 1
                    CREATE (s)-[e:{label}]->(t)
                    DELETE e
                    RETURN 1
                """
                q_bootstrap = sql.SQL("""
                    SELECT * FROM ag_catalog.cypher({}::name, $cypher$
                    {cypher}
                    $cypher$) AS (ok ag_catalog.agtype);
                """.replace("{cypher}", cypher_bootstrap)).format(sql.Literal(self.graph))
                await cur.execute(q_bootstrap)
                await self._conn.commit()

        table = sql.Identifier(self.graph, label)
        inserted = 0
        num_chunks = (total_count + chunk_size - 1) // chunk_size
        for chunk_idx, i in enumerate(range(0, total_count, chunk_size), 1):
            chunk = edge_rows[i:i + chunk_size]
            values = []
            params: list[str] = []
            for edge in chunk:
                values.append(sql.SQL("(%s::ag_catalog.graphid, %s::ag_catalog.graphid, %s::ag_catalog.agtype)"))
                params.extend([
                    edge["src_vid"],
                    edge["dst_vid"],
                    json.dumps({"payload": edge["payload"]}),
                ])
            insert_sql = sql.SQL("INSERT INTO {} (start_id, end_id, properties) VALUES ").format(table) + sql.SQL(", ").join(values)
            async with self._conn.cursor() as cur:
                await cur.execute(insert_sql, params)
                inserted += len(chunk)
            await self._conn.commit()
            print(f"  [{label}] edges chunk {chunk_idx}/{num_chunks}  "
                  f"({inserted:,}/{total_count:,})", flush=True)
        return inserted


def _normalize_graph_data(graph_data: dict) -> tuple[dict[str, list[dict]], dict[str, list[dict]], int]:
    nodes = graph_data["graph"]["nodes"]
    links = graph_data["graph"]["links"]
    print(f"Normalizing {len(nodes):,} nodes and {len(links):,} links...", flush=True)
    t0 = time.time()

    nodes_by_label: dict[str, list[dict]] = {}
    id_to_node_label: dict[str, str] = {}
    raw_node_type_to_label: dict[str, str] = {}
    used_node_labels: set[str] = set()

    for node in nodes:
        node_id = str(node["id"])
        raw_type = node.get("type") or "Entity"
        if raw_type not in raw_node_type_to_label:
            raw_node_type_to_label[raw_type] = _unique_label(
                raw=raw_type,
                fallback="Entity",
                used_labels=used_node_labels,
            )
        node_label = raw_node_type_to_label[raw_type]
        payload = dict(node)
        payload["id"] = node_id
        payload["type"] = raw_type
        nodes_by_label.setdefault(node_label, []).append(payload)
        id_to_node_label[node_id] = node_label

    node_labels = set(nodes_by_label.keys())

    edges_by_label: dict[str, list[dict]] = {}
    skipped_missing_endpoint = 0
    remapped_edge_labels = 0
    raw_edge_type_to_label: dict[str, str] = {}
    used_edge_labels: set[str] = set()
    for link in links:
        src = str(link["source"])
        dst = str(link["target"])
        if src not in id_to_node_label or dst not in id_to_node_label:
            skipped_missing_endpoint += 1
            continue

        raw_edge_type = link.get("type") or "RELATED_TO"
        if raw_edge_type not in raw_edge_type_to_label:
            base_edge_label = _sanitize_label(raw_edge_type, "RELATED_TO")
            needs_remap = base_edge_label in node_labels
            if needs_remap:
                remapped_edge_labels += 1
            raw_edge_type_to_label[raw_edge_type] = _unique_label(
                raw=f"{raw_edge_type}{'_REL' if needs_remap else ''}",
                fallback="RELATED_TO",
                used_labels=used_edge_labels,
                reserved_labels=node_labels,
                suffix_hint="_REL",
            )
        edge_label = raw_edge_type_to_label[raw_edge_type]
        edge_payload = {k: v for k, v in link.items() if k not in ("source", "target", "type")}
        edge_payload["source"] = src
        edge_payload["target"] = dst
        edge_payload["type"] = link.get("type")
        edges_by_label.setdefault(edge_label, []).append(
            {"src_id": src, "dst_id": dst, "payload": edge_payload}
        )

    if remapped_edge_labels:
        print(f"Remapped {remapped_edge_labels} edge labels due to node/edge name collisions")

    elapsed = time.time() - t0
    print(f"Normalization complete in {elapsed:.1f}s  "
          f"({len(nodes_by_label)} node labels, {len(edges_by_label)} edge labels)", flush=True)

    return nodes_by_label, edges_by_label, skipped_missing_endpoint


async def _edge_worker(
    dsn: dict,
    graph: str,
    label: str,
    edge_rows: list[dict],
    sem: asyncio.Semaphore,
    chunk_size: int,
    progress: dict,
    max_retries: int = 3,
) -> int:
    """Insert all edges for one label using a dedicated connection with retry."""
    _validate_label(label)
    async with sem:
        last_exc: Exception | None = None
        for attempt in range(1, max_retries + 1):
            conn = None
            try:
                conn = await psycopg.AsyncConnection.connect(
                    **{**dsn, "connect_timeout": 60}
                )
                async with conn.cursor() as cur:
                    await cur.execute('SET search_path = ag_catalog, "$user", public;')
                    await cur.execute(
                        """SELECT 1 FROM ag_catalog.ag_label l
                           JOIN ag_catalog.ag_graph g ON l.graph = g.graphid
                           WHERE l.name = %s AND g.name = %s;""",
                        (label, graph),
                    )
                    if not await cur.fetchone():
                        cypher_bootstrap = f"""
                            MATCH (s)
                            WITH s LIMIT 1
                            MATCH (t)
                            WITH s, t LIMIT 1
                            CREATE (s)-[e:{label}]->(t)
                            DELETE e
                            RETURN 1
                        """
                        q_bootstrap = sql.SQL("""
                            SELECT * FROM ag_catalog.cypher({}::name, $cypher$
                            {cypher}
                            $cypher$) AS (ok ag_catalog.agtype);
                        """.replace("{cypher}", cypher_bootstrap)).format(sql.Literal(graph))
                        await cur.execute(q_bootstrap)
                        await conn.commit()

                table = sql.Identifier(graph, label)
                inserted = 0
                for i in range(0, len(edge_rows), chunk_size):
                    chunk = edge_rows[i : i + chunk_size]
                    values = [
                        sql.SQL("(%s::ag_catalog.graphid, %s::ag_catalog.graphid, %s::ag_catalog.agtype)")
                        for _ in chunk
                    ]
                    params: list[str] = []
                    for edge in chunk:
                        params.extend([
                            edge["src_vid"],
                            edge["dst_vid"],
                            json.dumps({"payload": edge["payload"]}),
                        ])
                    insert_sql = (
                        sql.SQL("INSERT INTO {} (start_id, end_id, properties) VALUES ").format(table)
                        + sql.SQL(", ").join(values)
                    )
                    async with conn.cursor() as cur:
                        await cur.execute(insert_sql, params)
                        inserted += len(chunk)
                    await conn.commit()

                progress["done"] += 1
                progress["edges"] += inserted
                done = progress["done"]
                total = progress["total"]
                if done % 100 == 0 or done == total or done <= 5:
                    print(
                        f"  Edge progress: {done}/{total} labels, "
                        f"{progress['edges']:,} edges inserted",
                        flush=True,
                    )
                return inserted

            except Exception as exc:
                last_exc = exc
                if conn:
                    try:
                        await conn.close()
                    except Exception:
                        pass
                    conn = None
                if attempt < max_retries:
                    delay = 2 ** attempt
                    print(
                        f"  RETRY [{label}] attempt {attempt}/{max_retries}: "
                        f"{exc} (waiting {delay}s)",
                        flush=True,
                    )
                    await asyncio.sleep(delay)
                else:
                    progress["done"] += 1
                    print(f"  FAILED [{label}] after {max_retries} attempts: {exc}", flush=True)
                    raise
            finally:
                if conn:
                    try:
                        await conn.close()
                    except Exception:
                        pass
        raise last_exc  # unreachable but satisfies type checker


async def load_graph_data() -> None:
    started = time.time()

    print(f"Using DSN: host={DSN['host']} port={DSN['port']} dbname={DSN['dbname']} user={DSN['user']}")
    print(f"Using graph: {GRAPH}")
    print(f"Reading graph data from: {GRAPH_DATA_FILE}", flush=True)
    graph_data = _read_graph_json(GRAPH_DATA_FILE)
    nodes_by_label, edges_by_label, skipped_missing_endpoint = _normalize_graph_data(graph_data)
    print(flush=True)

    helper = await PGAgeHelper.create(DSN, GRAPH)
    try:
        total_nodes = 0
        id_to_vertex: dict[str, str] = {}
        node_label_items = list(nodes_by_label.items())
        for li, (label, payload_rows) in enumerate(node_label_items, 1):
            print(f"\n[{li}/{len(node_label_items)}] Loading nodes: label={label}, count={len(payload_rows):,}", flush=True)
            t_label = time.time()
            id_map = await helper.batch_insert_nodes(label, payload_rows, chunk_size=CHUNK_SIZE)
            id_to_vertex.update(id_map)
            total_nodes += len(id_map)
            print(f"  [{label}] done in {time.time() - t_label:.1f}s  (total nodes so far: {total_nodes:,})", flush=True)

        total_edges = 0
        skipped_no_vertex = 0
        edge_label_items = list(edges_by_label.items())

        # Prepare all edge data (resolve vertex IDs)
        prepared_edges: list[tuple[str, list[dict]]] = []
        for edge_label, edge_rows in edge_label_items:
            to_insert: list[dict] = []
            for edge in edge_rows:
                src_vid = id_to_vertex.get(edge["src_id"])
                dst_vid = id_to_vertex.get(edge["dst_id"])
                if not src_vid or not dst_vid:
                    skipped_no_vertex += 1
                    continue
                to_insert.append({
                    "src_vid": src_vid,
                    "dst_vid": dst_vid,
                    "payload": edge["payload"],
                })
            if to_insert:
                prepared_edges.append((edge_label, to_insert))

        print(
            f"\nLoading {len(prepared_edges)} edge labels in parallel "
            f"(concurrency={PARALLEL_EDGES})...",
            flush=True,
        )
        t_edges = time.time()
        sem = asyncio.Semaphore(PARALLEL_EDGES)
        progress = {"done": 0, "total": len(prepared_edges), "edges": 0}
        tasks = [
            _edge_worker(DSN, GRAPH, label, rows, sem, CHUNK_SIZE, progress)
            for label, rows in prepared_edges
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        errors = []
        for (label, _), result in zip(prepared_edges, results):
            if isinstance(result, Exception):
                errors.append((label, result))
            else:
                total_edges += result

        print(
            f"\nAll edges loaded in {time.time() - t_edges:.1f}s  "
            f"({total_edges:,} edges across {len(prepared_edges)} labels)",
            flush=True,
        )
        if errors:
            print(f"  {len(errors)} edge labels FAILED:", flush=True)
            for label, exc in errors[:10]:
                print(f"    [{label}]: {exc}", flush=True)

        elapsed = time.time() - started
        print("\nLoad complete")
        print(f"Inserted nodes: {total_nodes}")
        print(f"Inserted edges: {total_edges}")
        print(f"Skipped links with missing source/target node: {skipped_missing_endpoint}")
        print(f"Skipped links with unresolved vertex IDs: {skipped_no_vertex}")
        print(f"Total time: {elapsed:.2f}s")
    finally:
        await helper.close()


if __name__ == "__main__":
    if os.name == "nt":
        asyncio.run(
            load_graph_data(),
            loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
        )
    else:
        asyncio.run(load_graph_data())