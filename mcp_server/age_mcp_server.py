import sys, asyncio
import os
import logging

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    # Force pure-python psycopg on Windows if libpq is available —
    # the binary backend's bundled libpq has SSL issues with Azure PostgreSQL on Python 3.13+
    try:
        import psycopg.pq._pq_ctypes  # noqa: F401 — test if libpq is importable
        os.environ.setdefault("PSYCOPG_IMPL", "python")
    except (ImportError, OSError):
        pass  # no system libpq — keep using binary backend
from typing import Annotated
from fastmcp import FastMCP
from dotenv import load_dotenv
from pg_age_helper import PGAgeHelper

# --- File logging ---
_log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(_log_dir, exist_ok=True)
_log_file = os.path.join(_log_dir, "age_mcp_server.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    handlers=[
        logging.FileHandler(_log_file, encoding="utf-8"),
        logging.StreamHandler(),  # keep console output too
    ],
)
logger = logging.getLogger("age_mcp")
logger.info(f"Logging to {_log_file}")


load_dotenv()

mcp = FastMCP("Graph Age MCP Server")


def _strip_agtype(val) -> str:
    """Strip AGE agtype formatting: '["Label"]' -> 'Label', '"rel"' -> 'rel'."""
    if not isinstance(val, str):
        return str(val)
    val = val.strip()
    if val.startswith('["') and val.endswith('"]'):
        val = val[2:-2]
    elif val.startswith('"') and val.endswith('"') and len(val) > 1:
        val = val[1:-1]
    return val

GRAPH_NAME = os.getenv("GRAPH_NAME", "")
_ONTOLOGY_MEMORY: dict[str, str] = {}


@mcp.tool
async def save_ontology(
    ontology: Annotated[str, "Generated ontology content to store in memory"],
    graph_name: Annotated[str | None, "Graph name for ontology cache key"] = None,
) -> dict:
    """
    Save the generated ontology in process memory.
    Args:
        ontology: The ontology content as text.
    Returns:
        Status indicating ontology was saved.
    """
    graph_key = (graph_name or GRAPH_NAME or "default").strip()
    _ONTOLOGY_MEMORY[graph_key] = ontology

    print("Ontology saved in memory for graph:", graph_key, "length:", len(ontology))
    return {
        "status": "saved",
        "has_ontology": True,
        "graph_name": graph_key,
        "length": len(ontology),
    }


@mcp.tool
async def fetch_ontology(
    graph_name: Annotated[str | None, "Graph name for ontology cache lookup"] = None,
) -> dict:
    """
    Fetch the ontology previously saved in process memory.
    Returns:
        The saved ontology content, if any.
    """
    graph_key = (graph_name or GRAPH_NAME or "default").strip()
    ontology = _ONTOLOGY_MEMORY.get(graph_key)
    print("Fetching ontology from memory for graph:", graph_key, "has ontology:", ontology is not None)
    return {
        "has_ontology": ontology is not None,
        "graph_name": graph_key,
        "ontology": ontology,
    }

@mcp.tool
async def resolve_entity_ids(
    search_term: Annotated[str, "The search term to find entities (e.g., a person name, topic)"],
    graph_name: Annotated[str, "Graph name to query for edges (e.g., 'meetings_graph_v2')"],
    node_label: Annotated[str, "The node label to filter results to (case-sensitive). Use empty string '' to search ALL labels."] = "",
    id_property: Annotated[str, "Dot-separated path to the ID property. Default: payload.id"] = "payload.id",
) -> dict:
    """
    Find entities matching a search term, then discover their edges and related node types.
    Returns entity IDs grouped by label PLUS outbound/inbound edge types for the top-ranked label.
    This gives the agent everything needed to build a query in one call.

    Args:
        search_term: The search term to look up via full-text search.
        graph_name: The graph to query for edge discovery.
        node_label: Exact node label to filter to. Empty string = search all labels.
        id_property: Dot-separated path to the ID field (default: payload.id).
    Returns:
        A dict with:
        - ids_by_label: dict mapping label -> list of entity IDs
        - anchor_label: the best-matching label (most IDs)
        - anchor_ids: the IDs for the anchor label
        - outbound_edges: list of {rel, target_label, count} from anchor nodes
        - inbound_edges: list of {source_label, rel, count} into anchor nodes
        - search_term: the original search term
    """
    # Normalize node_label in case it arrives in agtype format: ["Label"] -> Label
    if node_label:
        node_label = _strip_agtype(node_label)

    # Build the JSON extraction chain from the dot-separated path
    parts = id_property.split(".")
    json_path = "props"
    for part in parts[:-1]:
        json_path += f"->'{part}'"
    json_path += f"->>'{parts[-1]}'"

    sql = f"""
        SELECT {json_path} AS entity_id, node_label
        FROM public.search_graph_nodes('{search_term.replace("'", "''")}')
        {"WHERE node_label = '" + node_label.replace("'", "''") + "'" if node_label else ""}
        ORDER BY rank DESC;
    """
    print(f"[resolve_entity_ids] search_term={search_term}, node_label={node_label or '(all)'}")
    print(f"[resolve_entity_ids] SQL: {sql}")

    rows = await pg_helper.query_using_sql_cypher(sql, None)

    # Fallback: retry with shorter terms if nothing found
    if not rows:
        words = search_term.split()
        retry_terms = []
        for trim_count in range(1, min(3, len(words))):
            shorter = " ".join(words[: len(words) - trim_count])
            if len(shorter.split()) >= 2 and shorter not in retry_terms:
                retry_terms.append(shorter)
        for trim_count in range(1, min(3, len(words))):
            shorter = " ".join(words[trim_count:])
            if len(shorter.split()) >= 2 and shorter not in retry_terms:
                retry_terms.append(shorter)
        if len(words) >= 2:
            for w in words:
                if len(w) >= 3 and w not in retry_terms:
                    retry_terms.append(w)

        for shorter in retry_terms:
            sql_retry = f"""
                SELECT {json_path} AS entity_id, node_label
                FROM public.search_graph_nodes('{shorter.replace("'", "''")}')
                {"WHERE node_label = '" + node_label.replace("'", "''") + "'" if node_label else ""}
                ORDER BY rank DESC;
            """
            print(f"[resolve_entity_ids] Retry with shorter term: {shorter}")
            rows = await pg_helper.query_using_sql_cypher(sql_retry, None)
            if rows:
                break

    # Group IDs by label — cap at 10 IDs per label to save context
    ids_by_label: dict[str, list[str]] = {}
    for row in rows:
        eid = row.get("entity_id")
        lbl = row.get("node_label")
        if eid is not None and lbl is not None:
            ids_by_label.setdefault(lbl, [])
            if eid not in ids_by_label[lbl] and len(ids_by_label[lbl]) < 10:
                ids_by_label[lbl].append(eid)

    if not ids_by_label:
        return {
            "ids_by_label": {},
            "anchor_label": None,
            "anchor_ids": [],
            "outbound_edges": [],
            "inbound_edges": [],
            "search_term": search_term,
            "hint": "No entities found. Try a different search term or drop titles (Mayor, Dr., etc.)",
        }

    # If no node_label specified, return compact summary — label counts only, not all IDs
    if not node_label:
        label_summary = {_strip_agtype(lbl): len(ids) for lbl, ids in ids_by_label.items()}
        return {
            "labels_found": label_summary,
            "anchor_label": None,
            "anchor_ids": [],
            "outbound_edges": [],
            "inbound_edges": [],
            "search_term": search_term,
            "hint": "ERROR: node_label is required. Call discover_nodes first to find the correct label, then call resolve_entity_ids again with node_label set.",
        }

    # node_label was specified — use it as anchor and discover edges
    anchor_label = node_label
    anchor_ids = ids_by_label.get(anchor_label, [])

    if not anchor_ids:
        return {
            "ids_by_label": ids_by_label,
            "anchor_label": anchor_label,
            "anchor_ids": [],
            "outbound_edges": [],
            "inbound_edges": [],
            "search_term": search_term,
            "hint": f"No IDs found for label '{anchor_label}'. Available labels: {list(ids_by_label.keys())}",
        }
    # Use up to 5 IDs for edge discovery to keep it fast
    sample_ids = anchor_ids[:5]
    safe_ids = ", ".join(f"'{eid.replace(chr(39), chr(39)+chr(39))}'" for eid in sample_ids)
    cypher_id_path = ".".join(id_property.split("."))

    # Discover outbound edges
    outbound_edges = []
    try:
        out_sql = f"""SELECT * FROM ag_catalog.cypher('{graph_name}', $$
  MATCH (a:{anchor_label})-[r]->(b)
  WHERE a.{cypher_id_path} IN [{safe_ids}]
  RETURN type(r) AS rel, labels(b) AS tgt, count(*) AS cnt
$$) AS (rel ag_catalog.agtype, tgt ag_catalog.agtype, cnt ag_catalog.agtype);"""
        print(f"[resolve_entity_ids] Discovering outbound edges...")
        out_rows = await pg_helper.query_using_sql_cypher(out_sql, graph_name)
        outbound_edges = [{"rel": _strip_agtype(r["rel"]), "target_label": _strip_agtype(r["tgt"]), "count": r["cnt"]} for r in out_rows]
    except Exception as e:
        print(f"[resolve_entity_ids] Outbound edge discovery failed: {e}")

    # Discover inbound edges
    inbound_edges = []
    try:
        in_sql = f"""SELECT * FROM ag_catalog.cypher('{graph_name}', $$
  MATCH (a)-[r]->(b:{anchor_label})
  WHERE b.{cypher_id_path} IN [{safe_ids}]
  RETURN labels(a) AS src, type(r) AS rel, count(*) AS cnt
$$) AS (src ag_catalog.agtype, rel ag_catalog.agtype, cnt ag_catalog.agtype);"""
        print(f"[resolve_entity_ids] Discovering inbound edges...")
        in_rows = await pg_helper.query_using_sql_cypher(in_sql, graph_name)
        inbound_edges = [{"source_label": _strip_agtype(r["src"]), "rel": _strip_agtype(r["rel"]), "count": r["cnt"]} for r in in_rows]
    except Exception as e:
        print(f"[resolve_entity_ids] Inbound edge discovery failed: {e}")

    result = {
        "ids_by_label": ids_by_label,
        "anchor_label": anchor_label,
        "anchor_ids": anchor_ids,
        "outbound_edges": outbound_edges,
        "inbound_edges": inbound_edges,
        "search_term": search_term,
    }
    print(f"[resolve_entity_ids] anchor_label={anchor_label}, anchor_ids={len(anchor_ids)}, outbound={len(outbound_edges)}, inbound={len(inbound_edges)}")
    return result


# @mcp.tool
async def find_related_nodes(
    entity_ids: Annotated[list[str], "List of anchor entity IDs to find related nodes for"],
    anchor_label: Annotated[str, "The node label of the anchor entities (e.g., 'Product', 'Event')"],
    target_label: Annotated[str, "The node label to search for related nodes (e.g., 'Person', 'Organization')"],
    graph_name: Annotated[str, "Graph name to query"],
    id_property: Annotated[str, "Dot-separated path to the ID property (default: payload.id)"] = "payload.id",
) -> dict:
    """
    Find nodes of a target label that share source documents with the given anchor entities.
    Uses source-based co-occurrence: two nodes sharing a payload.sources entry means they
    participated in the same document/event context.

    Use this AFTER resolve_entity_ids when the user's question implies a related entity
    (e.g., "Who is the contact person for X?", "Who presented Y?", "What staff worked on Z?").

    Args:
        entity_ids: The anchor entity IDs (from resolve_entity_ids).
        anchor_label: Node label of the anchor (e.g., Product, Event).
        target_label: Node label to search for related nodes (e.g., Person, Organization).
        graph_name: The graph to query.
        id_property: Dot-separated path to the entity ID field.
    Returns:
        A dict with related_nodes (list of {id, name, properties}), count, and the query used.
    """
    # Build the Cypher property access from dot-separated path
    cypher_id_path = ".".join(f"{p}" for p in id_property.split("."))

    # Sanitize entity IDs to prevent injection
    safe_ids = ", ".join(f"'{eid.replace(chr(39), chr(39)+chr(39))}'" for eid in entity_ids)

    sql = f"""SELECT * FROM ag_catalog.cypher('{graph_name}', $$
  MATCH (anchor:{anchor_label}) WHERE anchor.{cypher_id_path} IN [{safe_ids}]
  UNWIND coalesce(anchor.payload.sources, []) AS src
  WITH DISTINCT src
  MATCH (related:{target_label}) WHERE related.payload.sources IS NOT NULL
  UNWIND coalesce(related.payload.sources, []) AS rsrc
  WITH related, rsrc, src WHERE rsrc = src
  RETURN DISTINCT related.{cypher_id_path} AS id, related.payload.name AS name, related.payload.attributes AS properties
$$) AS (id ag_catalog.agtype, name ag_catalog.agtype, properties ag_catalog.agtype);"""

    print(f"[find_related_nodes] anchor_label={anchor_label}, target_label={target_label}, entity_ids_count={len(entity_ids)}")
    print(f"[find_related_nodes] SQL: {sql}")

    try:
        rows = await pg_helper.query_using_sql_cypher(sql, graph_name)
    except Exception as e:
        return {
            "related_nodes": [],
            "count": 0,
            "error": str(e),
            "query": sql,
        }

    print(f"[find_related_nodes] Found {len(rows)} related nodes")
    return {
        "related_nodes": rows,
        "count": len(rows),
        "anchor_label": anchor_label,
        "target_label": target_label,
        "query": sql,
    }


@mcp.tool
async def discover_nodes(
    graph_name: Annotated[str, "Graph name to query (e.g., 'meetings_graph_v2')"],
) -> list[dict]:
    """
    Discover all distinct node labels and their property structure.
    Returns a compact summary: label name + key property paths (not full payloads).
    Args:
        graph_name: The graph to query.
    Returns:
        A list of dicts with 'label' and 'property_paths' for each distinct node type.
    """
    sql = f"""SELECT * FROM ag_catalog.cypher('{graph_name}', $$
  MATCH (n) WHERE n.payload IS NOT NULL
  RETURN labels(n) AS label, head(collect(n.payload)) AS sample_payload
$$) AS (label ag_catalog.agtype, sample_payload ag_catalog.agtype);"""

    print(f"[discover_nodes] graph_name={graph_name}")
    rows = await pg_helper.query_using_sql_cypher(sql, graph_name)
    print(f"[discover_nodes] Found {len(rows)} distinct node labels")

    # Extract compact summaries — just label + key property paths
    import json
    compact = []
    for row in rows:
        label = row.get("label", "")
        sample = row.get("sample_payload", "{}")
        # Parse the sample payload to extract property paths
        try:
            if isinstance(sample, str):
                payload = json.loads(sample)
            else:
                payload = sample
        except (json.JSONDecodeError, TypeError):
            payload = {}

        # Extract top-level keys and attributes keys — show as FULL CYPHER PATHS
        top_keys = list(payload.keys()) if isinstance(payload, dict) else []
        property_paths = [f"n.payload.{k}" for k in top_keys]

        attr_keys = []
        if isinstance(payload, dict) and "attributes" in payload and isinstance(payload["attributes"], dict):
            attr_keys = list(payload["attributes"].keys())
            property_paths.extend([f"n.payload.attributes.{k}" for k in attr_keys])

        has_sources = "sources" in top_keys
        sample_name = payload.get("name", "") if isinstance(payload, dict) else ""
        # Truncate name to 60 chars
        if len(sample_name) > 60:
            sample_name = sample_name[:60] + "..."

        compact.append({
            "label": _strip_agtype(label),
            "sample_name": sample_name,
            "property_paths": property_paths,
            "has_sources": has_sources,
        })

    return compact


@mcp.tool
async def search_graph(
    search_term: Annotated[str, "The text to search for (person name, agenda item title, meeting name, etc.)"],
    graph_name: Annotated[str, "Graph name (e.g., 'meetings_graph_v2')"],
    label_filter: Annotated[str, "Optional: filter results to a specific node label (e.g., 'Councilmember', 'City_Council_Meeting'). Empty string for all labels."] = "",
    max_results: Annotated[int, "Maximum number of results to return (default 10)"] = 10,
) -> dict:
    """
    Search graph nodes using full-text search. Returns matching nodes with their labels, names, IDs, and properties.
    Use this to find entities mentioned in the user's question before writing a Cypher query.

    Args:
        search_term: The text to search for.
        graph_name: The graph name.
        label_filter: Optional node label to filter results.
        max_results: Max results to return.
    Returns:
        A dict with:
        - results: list of {node_label, entity_id, name, properties} for each match
        - search_term: the original search term
    """
    print(f"[search_graph] search_term={search_term}, label_filter={label_filter or '(all)'}, max_results={max_results}")

    label_clause = f"WHERE node_label = '{label_filter.replace(chr(39), chr(39)+chr(39))}'" if label_filter else ""

    sql = f"""
        SELECT props->'payload'->>'id' AS entity_id,
               node_label,
               props->'payload'->>'name' AS name,
               props->'payload' AS payload,
               rank
        FROM public.search_graph_nodes('{search_term.replace(chr(39), chr(39)+chr(39))}')
        {label_clause}
        ORDER BY rank DESC
        LIMIT {max_results};
    """

    rows = await pg_helper.query_using_sql_cypher(sql, None)
    print(f"[search_graph] Found {len(rows)} results")

    # If no results, try progressively shorter search terms
    if not rows and len(search_term.split()) > 1:
        words = search_term.split()
        for trim in range(1, min(4, len(words))):
            shorter = " ".join(words[:len(words) - trim])
            if len(shorter) < 3:
                break
            retry_sql = f"""
                SELECT props->'payload'->>'id' AS entity_id,
                       node_label,
                       props->'payload'->>'name' AS name,
                       props->'payload' AS payload,
                       rank
                FROM public.search_graph_nodes('{shorter.replace(chr(39), chr(39)+chr(39))}')
                {label_clause}
                ORDER BY rank DESC
                LIMIT {max_results};
            """
            rows = await pg_helper.query_using_sql_cypher(retry_sql, None)
            if rows:
                print(f"[search_graph] Retry with '{shorter}' found {len(rows)} results")
                break

    # Group by label for summary
    from collections import Counter
    label_counts = Counter(r.get("node_label", "") for r in rows)

    # Compact results — include payload for top results only to save context
    compact_results = []
    for r in rows:
        entry = {
            "entity_id": r.get("entity_id"),
            "node_label": r.get("node_label"),
            "name": r.get("name"),
        }
        # Include full payload only for top 3 results
        if len(compact_results) < 3:
            import json as _json
            try:
                payload = r.get("payload")
                if isinstance(payload, str):
                    payload = _json.loads(payload)
                entry["payload"] = payload
            except Exception:
                pass
        compact_results.append(entry)

    return {
        "results": compact_results,
        "label_summary": dict(label_counts),
        "search_term": search_term,
        "total_found": len(rows),
    }


@mcp.tool
async def query_using_sql_cypher(
    sql_query: Annotated[str, "SQL Query"],
    graph_name: Annotated[str, "Graph name to use for ag_catalog.cypher(...)"]
) -> list[dict]:
    """
    Execute the sql statement against a PostgreSQL database with the AGE extension.
    The sql query is generated by another agent. This tool simply executes the query and returns the result.
    Args:
        sql_query: The SQL query to execute.
        graph_name: Graph name to use when executing AGE cypher calls.
    Returns:
        The query result as a list of dictionaries.
    """
    rows = await pg_helper.query_using_sql_cypher(sql_query, graph_name)
    print("Query executed, result:\n", rows)
    return rows


@mcp.tool
async def build_query_context(
    search_term: Annotated[str, "The entity name to search for (e.g., 'Larry Klein'). Drop titles like Mayor, Dr., etc."],
    target_concept: Annotated[str, "What the user is asking about — one word (e.g., 'meetings', 'votes', 'agenda items')"],
    graph_name: Annotated[str, "Graph name (e.g., 'meetings_graph_v2')"],
    year: Annotated[str, "Year filter if mentioned in the question (e.g., '2022'). Empty string if no year."] = "",
) -> dict:
    """
    One-shot pipeline: discovers schema, finds entity, discovers edges, and builds a ready-to-use SQL query.
    Call this ONCE with the extracted parameters, then emit the suggested_query as your FINAL_SQL.

    Returns:
        - anchor_label, anchor_ids: the entity found
        - matching_edges: edges connecting the entity to the target concept
        - suggested_query: a complete, ready-to-use SQL+Cypher query (emit this as FINAL_SQL)
        - error: if something went wrong
    """
    import json as _json
    print(f"[build_query_context] search_term={search_term}, target_concept={target_concept}, graph_name={graph_name}, year={year}")

    # --- Step 1: Discover node labels ---
    discover_sql = f"""SELECT * FROM ag_catalog.cypher('{graph_name}', $$
  MATCH (n) WHERE n.payload IS NOT NULL
  RETURN labels(n) AS label, head(collect(n.payload)) AS sample_payload
$$) AS (label ag_catalog.agtype, sample_payload ag_catalog.agtype);"""

    try:
        disc_rows = await pg_helper.query_using_sql_cypher(discover_sql, graph_name)
    except Exception as e:
        return {"error": f"Schema discovery failed: {e}"}

    # Parse labels and find date field
    all_labels = []
    date_field = "date"  # default
    for row in disc_rows:
        lbl = _strip_agtype(row.get("label", ""))
        all_labels.append(lbl)
        sample = row.get("sample_payload", "{}")
        try:
            payload = _json.loads(sample) if isinstance(sample, str) else sample
        except Exception:
            payload = {}
        if isinstance(payload, dict):
            attrs = payload.get("attributes", {})
            if isinstance(attrs, dict) and "date" in attrs:
                date_field = "date"

    print(f"[build_query_context] Found labels: {all_labels}")

    # --- Step 2: Find entity — search all labels first, then narrow ---
    anchor_label = None
    anchor_ids = []

    # Determine if the question is about a person doing something (attending, voting, presenting)
    _person_concepts = {"meeting", "vote", "attend", "present", "led", "report", "liaison", "appoint"}
    _is_person_query = any(kw in target_concept.lower() for kw in _person_concepts)
    _person_labels = {"Councilmember", "Commissioner", "Staff_Member", "Presenter", "Applicant_Owner"}

    # First try: search all labels at once
    search_sql_all = f"""
        SELECT props->'payload'->>'id' AS entity_id, node_label
        FROM public.search_graph_nodes('{search_term.replace("'", "''")}')
        ORDER BY rank DESC;
    """
    rows_all = await pg_helper.query_using_sql_cypher(search_sql_all, None)

    if rows_all:
        from collections import Counter
        label_counts = Counter(r.get("node_label", "") for r in rows_all)

        # For person-related queries, prefer person labels even if they have fewer matches
        if _is_person_query:
            person_matches = {lbl: cnt for lbl, cnt in label_counts.items() if lbl in _person_labels}
            if person_matches:
                anchor_label = max(person_matches, key=person_matches.get)
                print(f"[build_query_context] Person query detected, preferring '{anchor_label}' ({person_matches[anchor_label]} matches) over raw top '{label_counts.most_common(1)[0][0]}' ({label_counts.most_common(1)[0][1]} matches)")
            else:
                anchor_label = label_counts.most_common(1)[0][0]
        else:
            anchor_label = label_counts.most_common(1)[0][0]

        anchor_ids = list(dict.fromkeys(
            r["entity_id"] for r in rows_all
            if r.get("node_label") == anchor_label and r.get("entity_id")
        ))[:10]

    # If search with full term failed, retry with progressively shorter terms
    if not anchor_ids:
        words = search_term.split()
        for trim in range(1, min(4, len(words))):
            shorter = " ".join(words[:len(words) - trim])
            if len(shorter) < 3:
                break
            retry_sql = f"""
                SELECT props->'payload'->>'id' AS entity_id, node_label
                FROM public.search_graph_nodes('{shorter.replace("'", "''")}')
                ORDER BY rank DESC;
            """
            retry_rows = await pg_helper.query_using_sql_cypher(retry_sql, None)
            if retry_rows:
                from collections import Counter
                label_counts = Counter(r.get("node_label", "") for r in retry_rows)
                if _is_person_query:
                    person_matches = {lbl: cnt for lbl, cnt in label_counts.items() if lbl in _person_labels}
                    anchor_label = max(person_matches, key=person_matches.get) if person_matches else label_counts.most_common(1)[0][0]
                else:
                    anchor_label = label_counts.most_common(1)[0][0]
                anchor_ids = list(dict.fromkeys(
                    r["entity_id"] for r in retry_rows
                    if r.get("node_label") == anchor_label and r.get("entity_id")
                ))[:10]
                break

    if not anchor_ids:
        return {
            "error": f"Entity '{search_term}' not found in any label.",
            "all_labels": all_labels,
            "suggested_query": None,
        }

    print(f"[build_query_context] anchor_label={anchor_label}, anchor_ids={anchor_ids}")

    # --- Step 3: Discover edges ---
    safe_ids = ", ".join(f"'{eid}'" for eid in anchor_ids[:5])

    out_sql = f"""SELECT * FROM ag_catalog.cypher('{graph_name}', $$
  MATCH (a:{anchor_label})-[r]->(b)
  WHERE a.payload.id IN [{safe_ids}]
  RETURN type(r) AS rel, labels(b) AS tgt, count(*) AS cnt
$$) AS (rel ag_catalog.agtype, tgt ag_catalog.agtype, cnt ag_catalog.agtype);"""

    in_sql = f"""SELECT * FROM ag_catalog.cypher('{graph_name}', $$
  MATCH (a)-[r]->(b:{anchor_label})
  WHERE b.payload.id IN [{safe_ids}]
  RETURN labels(a) AS src, type(r) AS rel, count(*) AS cnt
$$) AS (src ag_catalog.agtype, rel ag_catalog.agtype, cnt ag_catalog.agtype);"""

    outbound = []
    inbound = []
    try:
        out_rows = await pg_helper.query_using_sql_cypher(out_sql, graph_name)
        outbound = [{"rel": _strip_agtype(r["rel"]), "target_label": _strip_agtype(r["tgt"]), "count": r["cnt"]} for r in out_rows]
    except Exception as e:
        print(f"[build_query_context] Outbound edge discovery failed: {e}")
    try:
        in_rows = await pg_helper.query_using_sql_cypher(in_sql, graph_name)
        inbound = [{"source_label": _strip_agtype(r["src"]), "rel": _strip_agtype(r["rel"]), "count": r["cnt"]} for r in in_rows]
    except Exception as e:
        print(f"[build_query_context] Inbound edge discovery failed: {e}")

    # --- Step 4: Build schema summary for the LLM ---
    # Instead of building a query server-side, give the LLM all the context it needs
    # to generate its own Cypher query.

    # Compact schema: just label names (LLM already knows property paths from instructions)
    schema_summary = {
        "node_labels": all_labels,
        "date_property_path": f"payload.attributes.{date_field}",
    }

    # Compact edge summary
    edge_summary = {
        "outbound": [f"(:{anchor_label})-[:{e['rel']}]->(:{e['target_label']})" for e in outbound],
        "inbound": [f"(:{e['source_label']})-[:{e['rel']}]->(:{anchor_label})" for e in inbound],
    }

    safe_id_list = ", ".join(f"'{eid}'" for eid in anchor_ids)

    result = {
        "anchor_label": anchor_label,
        "anchor_ids": anchor_ids,
        "anchor_id_cypher_filter": f"a.payload.id IN [{safe_id_list}]",
        "schema": schema_summary,
        "edges": edge_summary,
        "outbound_edges_raw": outbound,
        "inbound_edges_raw": inbound,
        "graph_name": graph_name,
        "year": year,
    }
    print(f"[build_query_context] Done. anchor={anchor_label}, ids={len(anchor_ids)}, outbound={len(outbound)}, inbound={len(inbound)}")
    return result


if __name__ == "__main__":
    import selectors
    global pg_helper
    # Python 3.13+ on Windows: asyncio.run() ignores event loop policy,
    # must pass loop_factory explicitly for psycopg async to work.
    _loop_factory = None
    if sys.platform.startswith("win"):
        _loop_factory = asyncio.SelectorEventLoop
    pg_helper = asyncio.run(PGAgeHelper.create(), loop_factory=_loop_factory)

    #test_query = """SELECT *
    #    FROM ag_catalog.cypher('customer_graph', $$
#
    #    MATCH (c:Customer)
    #    WHERE c.payload.name = 'Customer 002'
    #    OPTIONAL MATCH (c)-[:ADOPTED_PRODUCT]->(p:Product)
    #    RETURN c.payload.name AS customer_name, collect(DISTINCT p.payload.name) AS product_names
#
    #    $$) AS (
    #    customer_name ag_catalog.agtype,
    #    product_names ag_catalog.agtype
    #    );"""
    #
    #result = asyncio.run(query_using_sql_cypher(test_query))
    #print("Test query result:\n", result)

    mcp.run(transport="streamable-http", host="0.0.0.0", port=3002)