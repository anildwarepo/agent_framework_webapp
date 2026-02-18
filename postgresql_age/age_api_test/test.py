#!/usr/bin/env python3
import os
import re
import json
from typing import Any, Dict

import psycopg2
from psycopg2.pool import SimpleConnectionPool
from fastapi import FastAPI, HTTPException, Depends, Path
from pydantic import BaseModel, Field

# ---- Config (env-compatible, like your script) ----
DSN = dict(
    host=os.getenv("PGHOST", "localhost"),
    port=int(os.getenv("PGPORT", "5432")),
    dbname=os.getenv("PGDATABASE", "postgres"),
    user=os.getenv("PGUSER", "postgres"),
    password=os.getenv("PGPASSWORD", "postgres"),
)
DEFAULT_GRAPH = os.getenv("AGE_GRAPH", "age_smoke")

# If True, check AGE extension and ensure search_path for each connection
AGE_CHECK_ON_CONNECT = True

# ---- Pydantic schema for the request ----
class NodeIn(BaseModel):
    label: str = Field(..., description="Node label, e.g. 'TestNode'")
    properties: Dict[str, Any] = Field(
        default_factory=dict, description="Arbitrary properties for the node"
    )

# ---- FastAPI app / connection pool ----
app = FastAPI(title="AGE Node Creator")

_pool: SimpleConnectionPool | None = None

LABEL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

def _ensure_age_ready(cur) -> None:
    # extension installed?
    cur.execute("SELECT 1 FROM pg_extension WHERE extname='age';")
    if not cur.fetchone():
        raise RuntimeError(
            "AGE extension is not installed in this database. "
            "Run: CREATE EXTENSION age; (as superuser)"
        )
    # search path: ag_catalog first so `ag_catalog.cypher` resolves cleanly
    cur.execute('SET search_path = ag_catalog, "$user", public;')

def _get_conn():
    if _pool is None:
        raise RuntimeError("Connection pool not initialized")
    conn = _pool.getconn()
    conn.autocommit = True
    if AGE_CHECK_ON_CONNECT:
        with conn.cursor() as cur:
            _ensure_age_ready(cur)
    return conn

def _put_conn(conn):
    if _pool is not None and conn is not None:
        _pool.putconn(conn)

@app.on_event("startup")
def _startup() -> None:
    global _pool
    _pool = SimpleConnectionPool(minconn=1, maxconn=5, **DSN)

@app.on_event("shutdown")
def _shutdown() -> None:
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None

# ---- Helper: safe label + cypher exec returning JSON ----
def _create_node_as_json(graph: str, label: str, props: Dict[str, Any]) -> Dict[str, Any]:
    if not LABEL_RE.match(label):
        raise HTTPException(status_code=400, detail="Invalid label. Use [A-Za-z_][A-Za-z0-9_]*")

    # Build the Cypher text with a validated label (labels can’t be parameterized)
    cypher_text = f"""
        CREATE (n:{label} {{}})
        SET n += $props
        RETURN n
    """

    # Pass parameters via the 3rd arg (params) to ag_catalog.cypher
    params_json = json.dumps({"props": props})

    sql = """
        SELECT ag_catalog.agtype_to_json(n) AS node_json
        FROM ag_catalog.cypher(%s, %s, %s::json::agtype)
        AS (n ag_catalog.agtype);
    """

    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (graph, cypher_text, params_json))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=500, detail="No row returned from AGE.")
            # row[0] is a JSON string; parse it to a Python dict for FastAPI
            return json.loads(row[0])
    finally:
        _put_conn(conn)

# ---- Endpoint ----
@app.post("/graphs/{graph}/nodes")
def create_node(
    item: NodeIn,
    graph: str = Path(default=DEFAULT_GRAPH, description="Graph name (created separately)"),
):
    """
    Create a node in the given AGE graph and return the created vertex as JSON.
    Payload example:
    {
      "label": "TestNode",
      "properties": {"name": "hello", "nps": 42}
    }
    """
    try:
        node_dict = _create_node_as_json(graph, item.label, item.properties)
        return {"graph": graph, "node": node_dict}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
