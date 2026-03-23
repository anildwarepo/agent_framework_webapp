-- ============================================================
-- Full-Text Search for Apache AGE Graph Nodes
-- ============================================================
-- Integrates PostgreSQL FTS with AGE graph tables so you can
-- search node properties (name, description, title, etc.)
-- loaded by load_meetings_graph.py.
--
-- USAGE:
--   1. Run load_meetings_graph.py first to populate the graph.
--   2. Then run this script:
--        psql -d <your_db> -f setup_fulltext_search.sql
--   3. Query the graph_node_search table.
-- ============================================================

SET search_path = ag_catalog, "$user", public;

-- Graph name — must match GRAPH_NAME / GRAPH env var from the loader
-- Uses a session-level custom GUC so it works in any SQL client.
SET app.graph_name = 'meetings_graph_v2';

-- ============================================================
-- 1. Materialized view: flatten all node labels into one
--    searchable table with a tsvector column.
-- ============================================================

-- Helper: extract all text values from a jsonb object (one level deep)
CREATE OR REPLACE FUNCTION public.jsonb_all_text_values(obj jsonb)
RETURNS text
LANGUAGE sql IMMUTABLE STRICT AS $$
    SELECT string_agg(value::text, ' ')
    FROM jsonb_each_text(obj);
$$;

-- Drop previous search artefacts if re-running
DROP MATERIALIZED VIEW IF EXISTS public.graph_node_search;

-- Build the materialized view dynamically from all vertex labels
-- in the target graph.
DO $$
DECLARE
    _graph_name text := current_setting('app.graph_name');
    _graphid    oid;
    _label      record;
    _union_parts text[] := '{}';
    _sql        text;
BEGIN
    -- Resolve graph OID
    SELECT graphid INTO _graphid
    FROM ag_catalog.ag_graph
    WHERE name = _graph_name;

    IF _graphid IS NULL THEN
        RAISE EXCEPTION 'Graph "%" not found. Run load_meetings_graph.py first.', _graph_name;
    END IF;

    -- Collect all vertex labels (kind = 'v'), skip the default _ag_label_vertex
    FOR _label IN
        SELECT l.name AS label_name
        FROM ag_catalog.ag_label l
        WHERE l.graph = _graphid
          AND l.kind = 'v'
          AND l.name <> '_ag_label_vertex'
        ORDER BY l.name
    LOOP
        _union_parts := array_append(_union_parts, format(
            $q$
            SELECT id,
                   %L::text AS node_label,
                   (properties::text)::jsonb AS props
            FROM %I.%I
            $q$,
            _label.label_name,
            _graph_name,
            _label.label_name
        ));
    END LOOP;

    IF array_length(_union_parts, 1) IS NULL THEN
        RAISE EXCEPTION 'No vertex labels found in graph "%".', _graph_name;
    END IF;

    _sql := format($m$
        CREATE MATERIALIZED VIEW public.graph_node_search AS
        SELECT
            id                                          AS vertex_id,
            node_label,
            props,
            -- Weighted tsvector:
            --   A = id / name / title  (high relevance)
            --   B = description / summary
            --   C = all other property text (catch-all)
            setweight(to_tsvector('english',
                coalesce(props->'payload'->>'name',
                         props->'payload'->>'title',
                         props->'payload'->>'id',
                         '')), 'A') ||
            setweight(to_tsvector('english',
                coalesce(props->'payload'->>'description',
                         props->'payload'->>'summary',
                         '')), 'B') ||
            setweight(to_tsvector('english',
                coalesce(public.jsonb_all_text_values(props->'payload'), '')), 'C')
            AS search_vector
        FROM (
            %s
        ) AS all_nodes
        WITH DATA;
    $m$, array_to_string(_union_parts, ' UNION ALL '));

    EXECUTE _sql;

    RAISE NOTICE 'Materialized view public.graph_node_search created.';
END
$$;

-- ============================================================
-- 2. Indexes
-- ============================================================

-- Unique index on vertex_id (required for REFRESH CONCURRENTLY)
CREATE UNIQUE INDEX IF NOT EXISTS idx_graph_node_search_pk
    ON public.graph_node_search (vertex_id);

-- GIN index for full-text search
CREATE INDEX IF NOT EXISTS idx_graph_node_search_fts
    ON public.graph_node_search USING GIN (search_vector);

-- B-tree on label for filtering by node type
CREATE INDEX IF NOT EXISTS idx_graph_node_search_label
    ON public.graph_node_search (node_label);

-- ============================================================
-- 3. Convenience: refresh function
-- ============================================================
-- Call after re-loading graph data:
--   SELECT public.refresh_graph_node_search();

CREATE OR REPLACE FUNCTION public.refresh_graph_node_search()
RETURNS void
LANGUAGE sql AS $$
    REFRESH MATERIALIZED VIEW CONCURRENTLY public.graph_node_search;
$$;

-- ============================================================
-- 4. Search helper function
-- ============================================================
-- Returns ranked results for a plain-language query.
-- Optional: filter by node_label.
--
-- Example:  SELECT * FROM public.search_graph_nodes('budget review');
--           SELECT * FROM public.search_graph_nodes('John', 'Person');

CREATE OR REPLACE FUNCTION public.search_graph_nodes(
    search_text text,
    label_filter text DEFAULT NULL,
    max_results  int  DEFAULT 25
)
RETURNS TABLE (
    vertex_id   ag_catalog.graphid,
    node_label  text,
    rank        real,
    props       jsonb
)
LANGUAGE sql STABLE AS $$
    SELECT
        s.vertex_id,
        s.node_label,
        ts_rank(s.search_vector, q) AS rank,
        s.props
    FROM public.graph_node_search s,
         websearch_to_tsquery('english', search_text) AS q
    WHERE s.search_vector @@ q
      AND (label_filter IS NULL OR s.node_label = label_filter)
    ORDER BY rank DESC
    LIMIT max_results;
$$;

-- ============================================================
-- 5. Example queries
-- ============================================================

-- 5a. Basic search across all node types
SELECT vertex_id, node_label, rank,
       props->'payload'->>'name' AS name
FROM public.search_graph_nodes('meeting');

-- 5b. Search only Person nodes
SELECT vertex_id, rank,
       props->'payload'->>'name' AS person_name
FROM public.search_graph_nodes('John', 'Person');

-- 5c. Direct query with boolean operators (AND / NOT)
SELECT vertex_id, node_label,
       ts_rank(search_vector, q) AS rank,
       props->'payload'->>'name' AS name
FROM public.graph_node_search,
     to_tsquery('english', 'budget & review & !draft') AS q
WHERE search_vector @@ q
ORDER BY rank DESC
LIMIT 20;

-- 5d. Phrase search — words must appear adjacent
SELECT vertex_id, node_label,
       props->'payload'->>'name' AS name
FROM public.graph_node_search,
     phraseto_tsquery('english', 'action items') AS q
WHERE search_vector @@ q
ORDER BY ts_rank(search_vector, q) DESC
LIMIT 20;

-- 5e. Prefix / autocomplete search
SELECT vertex_id, node_label,
       props->'payload'->>'name' AS name
FROM public.graph_node_search
WHERE search_vector @@ to_tsquery('english', 'meet:*')
LIMIT 20;

-- 5f. Highlighted snippets — show matching fragments
SELECT vertex_id, node_label,
       ts_headline('english',
           coalesce(public.jsonb_all_text_values(props->'payload'), ''),
           plainto_tsquery('english', 'budget review'),
           'StartSel=<<, StopSel=>>, MaxFragments=2, MaxWords=30'
       ) AS snippet
FROM public.graph_node_search
WHERE search_vector @@ plainto_tsquery('english', 'budget review')
ORDER BY ts_rank(search_vector, plainto_tsquery('english', 'budget review')) DESC
LIMIT 10;

-- 5g. Combine FTS with Cypher — find matching nodes then traverse edges
-- (Run the FTS first, then use the vertex_id in a Cypher MATCH)
--
-- Step 1: Get vertex IDs from FTS
--   SELECT vertex_id FROM public.search_graph_nodes('budget');
--
-- Step 2: Use in Cypher (replace <vid> with the actual ID)
--   SELECT * FROM ag_catalog.cypher('meetings_graph_v2', $$
--       MATCH (n)-[r]->(m)
--       WHERE id(n) = <vid>
--       RETURN n, type(r), m
--   $$) AS (n agtype, rel_type agtype, m agtype);

-- ============================================================
-- 6. Stats
-- ============================================================
SELECT node_label, count(*) AS node_count
FROM public.graph_node_search
GROUP BY node_label
ORDER BY node_count DESC;
