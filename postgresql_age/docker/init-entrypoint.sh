#!/usr/bin/env bash
set -euo pipefail

# ──────────────────────────────────────────────────────────────
# PostgreSQL AGE initialisation and graph data loader
# Mirrors azd_deploy/hooks/postprovision.ps1 — Phase 0
# ──────────────────────────────────────────────────────────────

MAX_RETRIES=${PG_INIT_MAX_RETRIES:-30}
RETRY_DELAY=${PG_INIT_RETRY_DELAY:-5}
GRAPH_NAME=${GRAPH_NAME:-customer_graph}
DATA_DIR=${DATA_DIR:-/app/data}

# If GRAPH_DATA_FILE is set but not an absolute path, prepend DATA_DIR.
if [ -n "${GRAPH_DATA_FILE:-}" ] && [ "${GRAPH_DATA_FILE#/}" = "${GRAPH_DATA_FILE}" ]; then
    GRAPH_DATA_FILE="${DATA_DIR}/${GRAPH_DATA_FILE}"
fi
export GRAPH_DATA_FILE=${GRAPH_DATA_FILE:-}

echo "=========================================="
echo "pg-init: PostgreSQL AGE initialization"
echo "=========================================="
echo "  PGHOST          = ${PGHOST:-localhost}"
echo "  PGPORT          = ${PGPORT:-5432}"
echo "  PGDATABASE      = ${PGDATABASE:-postgres}"
echo "  PGUSER          = ${PGUSER:-postgres}"
echo "  PGSSLMODE       = ${PGSSLMODE:-disable}"
echo "  GRAPH_NAME      = ${GRAPH_NAME}"
echo "  DATA_DIR        = ${DATA_DIR}"
echo "  GRAPH_DATA_FILE = ${GRAPH_DATA_FILE:-<default per loader>}"
echo ""

# ── 1. Wait for PostgreSQL to accept connections ──────────────
echo "[1/5] Waiting for PostgreSQL to be ready..."
attempt=0
until pg_isready -h "${PGHOST:-localhost}" -p "${PGPORT:-5432}" -U "${PGUSER:-postgres}" -d "${PGDATABASE:-postgres}" -q; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge "$MAX_RETRIES" ]; then
        echo "ERROR: PostgreSQL not ready after ${MAX_RETRIES} attempts. Exiting."
        exit 1
    fi
    echo "  Waiting for PostgreSQL (attempt ${attempt}/${MAX_RETRIES})..."
    sleep "$RETRY_DELAY"
done
echo "  PostgreSQL is ready."

# ── Check if data is already loaded (idempotent) ─────────────
# If the graph named $GRAPH_NAME already exists, skip all loading.
GRAPH_EXISTS=$(PGPASSWORD="${PGPASSWORD}" psql -h "${PGHOST:-localhost}" -p "${PGPORT:-5432}" -U "${PGUSER:-postgres}" -d "${PGDATABASE:-appdb}" -tAc \
  "SELECT count(*) FROM ag_catalog.ag_graph WHERE name='${GRAPH_NAME}';" 2>/dev/null || echo "0")

if [ "$GRAPH_EXISTS" = "1" ]; then
    echo ""
    echo "Graph '${GRAPH_NAME}' already loaded. Skipping initialization."
    echo "To force reload, remove the pg_age_data volume and restart."
    echo ""
    echo "=========================================="
    echo "pg-init: Already initialized — exiting."
    echo "=========================================="
    exit 0
fi

# ── 2. Enable AGE extension and set search_path ──────────────
echo ""
echo "[2/5] Enabling AGE extension and setting search_path..."
python /app/load_data/test_pg_connection.py

# ── 3. Load customer graph data ──────────────────────────────
echo ""
echo "[3/5] Loading customer graph data..."
python /app/load_data/customer_graph/load_customer_graph.py

# ── 4. Load meetings graph data ──────────────────────────────
echo ""
echo "[4/5] Loading meetings graph data..."
python /app/load_data/meetings_graph/load_meetings_graph.py

# ── 5. Build graph indexes ───────────────────────────────────
echo ""
echo "[5/5] Building graph indexes..."

if [ -f /app/load_data/customer_graph/build_graph_indexes.py ]; then
    echo "  Building customer_graph indexes..."
    python /app/load_data/customer_graph/build_graph_indexes.py
else
    echo "  Skipping customer_graph indexes (script not found)."
fi

if [ -f /app/load_data/meetings_graph/build_graph_indexes.py ]; then
    echo "  Building meetings_graph indexes..."
    python /app/load_data/meetings_graph/build_graph_indexes.py
else
    echo "  Skipping meetings_graph indexes (script not found)."
fi

echo ""
echo "=========================================="
echo "pg-init: Initialization complete!"
echo "=========================================="
