-- DROP-IN TEST SCRIPT (works around graphid cast errors)
-- Goal: verify indexes via EXPLAIN without touching AGE internals.
-- Trick: index the TEXT representation of graphid and compare on id::text.

BEGIN;

-- =========================
-- Functional indexes on TEXT (vertices)
-- =========================
CREATE UNIQUE INDEX IF NOT EXISTS idx_cg_customer_id_txt
  ON customer_graph."Customer" ((id::text));
CREATE UNIQUE INDEX IF NOT EXISTS idx_cg_contract_id_txt
  ON customer_graph."Contract" ((id::text));
CREATE UNIQUE INDEX IF NOT EXISTS idx_cg_product_id_txt
  ON customer_graph."Product" ((id::text));
CREATE UNIQUE INDEX IF NOT EXISTS idx_cg_feature_id_txt
  ON customer_graph."Feature" ((id::text));
CREATE UNIQUE INDEX IF NOT EXISTS idx_cg_opportunity_id_txt
  ON customer_graph."Opportunity" ((id::text));
CREATE UNIQUE INDEX IF NOT EXISTS idx_cg_supportcase_id_txt
  ON customer_graph."SupportCase" ((id::text));
CREATE UNIQUE INDEX IF NOT EXISTS idx_cg_qbrartifact_id_txt
  ON customer_graph."QBRArtifact" ((id::text));
CREATE UNIQUE INDEX IF NOT EXISTS idx_cg_telemetrymonth_id_txt
  ON customer_graph."TelemetryMonth" ((id::text));
CREATE UNIQUE INDEX IF NOT EXISTS idx_cg_communication_id_txt
  ON customer_graph."Communication" ((id::text));

-- =========================
-- Functional indexes on TEXT (edges)
-- =========================
-- ABOUT_AREA
CREATE UNIQUE INDEX IF NOT EXISTS idx_cg_about_area_id_txt
  ON customer_graph."ABOUT_AREA" ((id::text));
CREATE INDEX IF NOT EXISTS idx_cg_about_area_start_txt
  ON customer_graph."ABOUT_AREA" ((start_id::text));
CREATE INDEX IF NOT EXISTS idx_cg_about_area_end_txt
  ON customer_graph."ABOUT_AREA" ((end_id::text));
CREATE INDEX IF NOT EXISTS idx_cg_about_area_start_end_txt
  ON customer_graph."ABOUT_AREA" ((start_id::text), (end_id::text));

-- ADOPTED_FEATURE
CREATE UNIQUE INDEX IF NOT EXISTS idx_cg_adopted_feature_id_txt
  ON customer_graph."ADOPTED_FEATURE" ((id::text));
CREATE INDEX IF NOT EXISTS idx_cg_adopted_feature_start_txt
  ON customer_graph."ADOPTED_FEATURE" ((start_id::text));
CREATE INDEX IF NOT EXISTS idx_cg_adopted_feature_end_txt
  ON customer_graph."ADOPTED_FEATURE" ((end_id::text));
CREATE INDEX IF NOT EXISTS idx_cg_adopted_feature_start_end_txt
  ON customer_graph."ADOPTED_FEATURE" ((start_id::text), (end_id::text));

-- ADOPTED_PRODUCT
CREATE UNIQUE INDEX IF NOT EXISTS idx_cg_adopted_product_id_txt
  ON customer_graph."ADOPTED_PRODUCT" ((id::text));
CREATE INDEX IF NOT EXISTS idx_cg_adopted_product_start_txt
  ON customer_graph."ADOPTED_PRODUCT" ((start_id::text));
CREATE INDEX IF NOT EXISTS idx_cg_adopted_product_end_txt
  ON customer_graph."ADOPTED_PRODUCT" ((end_id::text));
CREATE INDEX IF NOT EXISTS idx_cg_adopted_product_start_end_txt
  ON customer_graph."ADOPTED_PRODUCT" ((start_id::text), (end_id::text));

-- HAD_COMM
CREATE UNIQUE INDEX IF NOT EXISTS idx_cg_had_comm_id_txt
  ON customer_graph."HAD_COMM" ((id::text));
CREATE INDEX IF NOT EXISTS idx_cg_had_comm_start_txt
  ON customer_graph."HAD_COMM" ((start_id::text));
CREATE INDEX IF NOT EXISTS idx_cg_had_comm_end_txt
  ON customer_graph."HAD_COMM" ((end_id::text));
CREATE INDEX IF NOT EXISTS idx_cg_had_comm_start_end_txt
  ON customer_graph."HAD_COMM" ((start_id::text), (end_id::text));

-- HAS_CONTRACT
CREATE UNIQUE INDEX IF NOT EXISTS idx_cg_has_contract_id_txt
  ON customer_graph."HAS_CONTRACT" ((id::text));
CREATE INDEX IF NOT EXISTS idx_cg_has_contract_start_txt
  ON customer_graph."HAS_CONTRACT" ((start_id::text));
CREATE INDEX IF NOT EXISTS idx_cg_has_contract_end_txt
  ON customer_graph."HAS_CONTRACT" ((end_id::text));
CREATE INDEX IF NOT EXISTS idx_cg_has_contract_start_end_txt
  ON customer_graph."HAS_CONTRACT" ((start_id::text), (end_id::text));

-- HAS_OPPORTUNITY
CREATE UNIQUE INDEX IF NOT EXISTS idx_cg_has_opportunity_id_txt
  ON customer_graph."HAS_OPPORTUNITY" ((id::text));
CREATE INDEX IF NOT EXISTS idx_cg_has_opportunity_start_txt
  ON customer_graph."HAS_OPPORTUNITY" ((start_id::text));
CREATE INDEX IF NOT EXISTS idx_cg_has_opportunity_end_txt
  ON customer_graph."HAS_OPPORTUNITY" ((end_id::text));
CREATE INDEX IF NOT EXISTS idx_cg_has_opportunity_start_end_txt
  ON customer_graph."HAS_OPPORTUNITY" ((start_id::text), (end_id::text));

-- HAS_QBR
CREATE UNIQUE INDEX IF NOT EXISTS idx_cg_has_qbr_id_txt
  ON customer_graph."HAS_QBR" ((id::text));
CREATE INDEX IF NOT EXISTS idx_cg_has_qbr_start_txt
  ON customer_graph."HAS_QBR" ((start_id::text));
CREATE INDEX IF NOT EXISTS idx_cg_has_qbr_end_txt
  ON customer_graph."HAS_QBR" ((end_id::text));
CREATE INDEX IF NOT EXISTS idx_cg_has_qbr_start_end_txt
  ON customer_graph."HAS_QBR" ((start_id::text), (end_id::text));

-- HAS_TELEMETRY
CREATE UNIQUE INDEX IF NOT EXISTS idx_cg_has_telemetry_id_txt
  ON customer_graph."HAS_TELEMETRY" ((id::text));
CREATE INDEX IF NOT EXISTS idx_cg_has_telemetry_start_txt
  ON customer_graph."HAS_TELEMETRY" ((start_id::text));
CREATE INDEX IF NOT EXISTS idx_cg_has_telemetry_end_txt
  ON customer_graph."HAS_TELEMETRY" ((end_id::text));
CREATE INDEX IF NOT EXISTS idx_cg_has_telemetry_start_end_txt
  ON customer_graph."HAS_TELEMETRY" ((start_id::text), (end_id::text));

-- RAISED_CASE
CREATE UNIQUE INDEX IF NOT EXISTS idx_cg_raised_case_id_txt
  ON customer_graph."RAISED_CASE" ((id::text));
CREATE INDEX IF NOT EXISTS idx_cg_raised_case_start_txt
  ON customer_graph."RAISED_CASE" ((start_id::text));
CREATE INDEX IF NOT EXISTS idx_cg_raised_case_end_txt
  ON customer_graph."RAISED_CASE" ((end_id::text));
CREATE INDEX IF NOT EXISTS idx_cg_raised_case_start_end_txt
  ON customer_graph."RAISED_CASE" ((start_id::text), (end_id::text));

COMMIT;

-- Refresh stats
ANALYZE customer_graph;

-- =========================
-- EXPLAIN tests (use id::text, start_id::text, end_id::text)
-- =========================

-- Vertex lookup by id::text (should use idx_cg_customer_id_txt)
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM customer_graph."Customer"
WHERE (id::text) = (
  SELECT (id::text) FROM customer_graph."Customer" ORDER BY id LIMIT 1
);

-- Edge lookups by start/end (should use *_start_txt / *_end_txt)
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM customer_graph."ADOPTED_PRODUCT"
WHERE (start_id::text) = (
  SELECT (start_id::text) FROM customer_graph."ADOPTED_PRODUCT" ORDER BY start_id LIMIT 1
);

EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM customer_graph."ADOPTED_PRODUCT"
WHERE (end_id::text) = (
  SELECT (end_id::text) FROM customer_graph."ADOPTED_PRODUCT" ORDER BY end_id LIMIT 1
);

-- Composite usage (start_id::text, end_id::text)
WITH k AS (
  SELECT (start_id::text) AS s, (end_id::text) AS e
  FROM customer_graph."HAS_OPPORTUNITY"
  ORDER BY 1,2
  LIMIT 1
)
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM customer_graph."HAS_OPPORTUNITY" x
JOIN k ON (x.start_id::text, x.end_id::text) = (k.s, k.e);

-- Inspect index usage after tests
SELECT
   schemaname,
   relname   AS table_name,
   indexrelname AS index_name,
   idx_scan, idx_tup_read, idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'customer_graph'
ORDER BY idx_scan DESC NULLS LAST, indexrelname;
