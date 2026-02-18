-- Create high-value indexes for your AGE graph labels in schema customer_graph.
-- Safe to run multiple times (IF NOT EXISTS).

BEGIN;

-- =========================
-- Vertex label indexes (UNIQUE on id)
-- =========================
CREATE UNIQUE INDEX IF NOT EXISTS idx_customer_graph_customer_id
  ON customer_graph."Customer"(id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_customer_graph_contract_id
  ON customer_graph."Contract"(id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_customer_graph_product_id
  ON customer_graph."Product"(id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_customer_graph_feature_id
  ON customer_graph."Feature"(id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_customer_graph_opportunity_id
  ON customer_graph."Opportunity"(id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_customer_graph_qbrartifact_id
  ON customer_graph."QBRArtifact"(id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_customer_graph_supportcase_id
  ON customer_graph."SupportCase"(id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_customer_graph_telemetrymonth_id
  ON customer_graph."TelemetryMonth"(id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_customer_graph_communication_id
  ON customer_graph."Communication"(id);

-- =========================
-- Edge label indexes
--   - UNIQUE on id
--   - Non-unique on start_id, end_id
--   - Composite on (start_id, end_id) for fast pattern lookups
-- =========================
CREATE UNIQUE INDEX IF NOT EXISTS idx_customer_graph_about_area_id
  ON customer_graph."ABOUT_AREA"(id);
CREATE INDEX IF NOT EXISTS idx_customer_graph_about_area_start
  ON customer_graph."ABOUT_AREA"(start_id);
CREATE INDEX IF NOT EXISTS idx_customer_graph_about_area_end
  ON customer_graph."ABOUT_AREA"(end_id);
CREATE INDEX IF NOT EXISTS idx_customer_graph_about_area_start_end
  ON customer_graph."ABOUT_AREA"(start_id, end_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_customer_graph_adopted_feature_id
  ON customer_graph."ADOPTED_FEATURE"(id);
CREATE INDEX IF NOT EXISTS idx_customer_graph_adopted_feature_start
  ON customer_graph."ADOPTED_FEATURE"(start_id);
CREATE INDEX IF NOT EXISTS idx_customer_graph_adopted_feature_end
  ON customer_graph."ADOPTED_FEATURE"(end_id);
CREATE INDEX IF NOT EXISTS idx_customer_graph_adopted_feature_start_end
  ON customer_graph."ADOPTED_FEATURE"(start_id, end_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_customer_graph_adopted_product_id
  ON customer_graph."ADOPTED_PRODUCT"(id);
CREATE INDEX IF NOT EXISTS idx_customer_graph_adopted_product_start
  ON customer_graph."ADOPTED_PRODUCT"(start_id);
CREATE INDEX IF NOT EXISTS idx_customer_graph_adopted_product_end
  ON customer_graph."ADOPTED_PRODUCT"(end_id);
CREATE INDEX IF NOT EXISTS idx_customer_graph_adopted_product_start_end
  ON customer_graph."ADOPTED_PRODUCT"(start_id, end_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_customer_graph_for_product_id
  ON customer_graph."FOR_PRODUCT"(id);
CREATE INDEX IF NOT EXISTS idx_customer_graph_for_product_start
  ON customer_graph."FOR_PRODUCT"(start_id);
CREATE INDEX IF NOT EXISTS idx_customer_graph_for_product_end
  ON customer_graph."FOR_PRODUCT"(end_id);
CREATE INDEX IF NOT EXISTS idx_customer_graph_for_product_start_end
  ON customer_graph."FOR_PRODUCT"(start_id, end_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_customer_graph_had_comm_id
  ON customer_graph."HAD_COMM"(id);
CREATE INDEX IF NOT EXISTS idx_customer_graph_had_comm_start
  ON customer_graph."HAD_COMM"(start_id);
CREATE INDEX IF NOT EXISTS idx_customer_graph_had_comm_end
  ON customer_graph."HAD_COMM"(end_id);
CREATE INDEX IF NOT EXISTS idx_customer_graph_had_comm_start_end
  ON customer_graph."HAD_COMM"(start_id, end_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_customer_graph_has_contract_id
  ON customer_graph."HAS_CONTRACT"(id);
CREATE INDEX IF NOT EXISTS idx_customer_graph_has_contract_start
  ON customer_graph."HAS_CONTRACT"(start_id);
CREATE INDEX IF NOT EXISTS idx_customer_graph_has_contract_end
  ON customer_graph."HAS_CONTRACT"(end_id);
CREATE INDEX IF NOT EXISTS idx_customer_graph_has_contract_start_end
  ON customer_graph."HAS_CONTRACT"(start_id, end_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_customer_graph_has_opportunity_id
  ON customer_graph."HAS_OPPORTUNITY"(id);
CREATE INDEX IF NOT EXISTS idx_customer_graph_has_opportunity_start
  ON customer_graph."HAS_OPPORTUNITY"(start_id);
CREATE INDEX IF NOT EXISTS idx_customer_graph_has_opportunity_end
  ON customer_graph."HAS_OPPORTUNITY"(end_id);
CREATE INDEX IF NOT EXISTS idx_customer_graph_has_opportunity_start_end
  ON customer_graph."HAS_OPPORTUNITY"(start_id, end_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_customer_graph_has_qbr_id
  ON customer_graph."HAS_QBR"(id);
CREATE INDEX IF NOT EXISTS idx_customer_graph_has_qbr_start
  ON customer_graph."HAS_QBR"(start_id);
CREATE INDEX IF NOT EXISTS idx_customer_graph_has_qbr_end
  ON customer_graph."HAS_QBR"(end_id);
CREATE INDEX IF NOT EXISTS idx_customer_graph_has_qbr_start_end
  ON customer_graph."HAS_QBR"(start_id, end_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_customer_graph_has_telemetry_id
  ON customer_graph."HAS_TELEMETRY"(id);
CREATE INDEX IF NOT EXISTS idx_customer_graph_has_telemetry_start
  ON customer_graph."HAS_TELEMETRY"(start_id);
CREATE INDEX IF NOT EXISTS idx_customer_graph_has_telemetry_end
  ON customer_graph."HAS_TELEMETRY"(end_id);
CREATE INDEX IF NOT EXISTS idx_customer_graph_has_telemetry_start_end
  ON customer_graph."HAS_TELEMETRY"(start_id, end_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_customer_graph_raised_case_id
  ON customer_graph."RAISED_CASE"(id);
CREATE INDEX IF NOT EXISTS idx_customer_graph_raised_case_start
  ON customer_graph."RAISED_CASE"(start_id);
CREATE INDEX IF NOT EXISTS idx_customer_graph_raised_case_end
  ON customer_graph."RAISED_CASE"(end_id);
CREATE INDEX IF NOT EXISTS idx_customer_graph_raised_case_start_end
  ON customer_graph."RAISED_CASE"(start_id, end_id);

COMMIT;
