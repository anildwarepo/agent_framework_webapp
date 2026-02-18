#!/bin/bash
#
# Post-provision hook to initialize PostgreSQL AGE, build containers, and deploy apps in sequence.
#

set -euo pipefail

MCP_SERVER_PATH="${1:-../../mcp_server}"
FASTAPI_PATH="${2:-../../af_fastapi}"
WEBAPP_PATH="${3:-../../webapp}"

get_azd_env() {
  azd env get-value "$1" 2>/dev/null | tr -d '\r'
}

set_azd_env() {
  azd env set "$1" "$2" >/dev/null
}

get_folder_hash() {
  local folder_path="$1"
  find "$folder_path" -type f \
    ! -path "*/__pycache__/*" \
    ! -path "*/node_modules/*" \
    ! -path "*/.git/*" \
    ! -name "*.pyc" \
    ! -name "*.pyo" \
    ! -path "*.egg-info/*" \
    -exec md5sum {} \; 2>/dev/null | sort | md5sum | cut -d' ' -f1
}

build_needed() {
  local folder_path="$1"
  local hash_env_var="$2"

  local current_hash
  current_hash=$(get_folder_hash "$folder_path")
  local stored_hash
  stored_hash=$(get_azd_env "$hash_env_var")

  if [ "$current_hash" = "$stored_hash" ]; then
    echo "false;$current_hash"
  else
    echo "true;$current_hash"
  fi
}

wait_postgres_ready() {
  local resource_group="$1"
  local server_name="$2"

  for attempt in {1..60}; do
    state=$(az postgres flexible-server show --resource-group "$resource_group" --name "$server_name" --query "state" -o tsv 2>/dev/null || true)
    if [ "$state" = "Ready" ]; then
      return 0
    fi
    echo "Waiting for PostgreSQL server to be Ready (attempt $attempt/60, current state: $state)..."
    sleep 10
  done

  echo "ERROR: PostgreSQL server did not reach Ready state in time."
  exit 1
}

ensure_postgres_allow_all_ips() {
  local resource_group="$1"
  local server_name="$2"

  if [ -z "$resource_group" ] || [ -z "$server_name" ]; then
    return
  fi

  echo "Opening PostgreSQL firewall to all IPs for data loading..."
  az postgres flexible-server firewall-rule create \
    --resource-group "$resource_group" \
    --name "$server_name" \
    --rule-name "AllowAllIps" \
    --start-ip-address "0.0.0.0" \
    --end-ip-address "255.255.255.255" >/dev/null
}

initialize_postgres_age_and_data() {
  local resource_group="$1"
  local server_name="$2"
  local admin_user="$3"
  local admin_password="$4"
  local server_fqdn="$5"
  local graph_name="$6"

  if [ -z "$server_name" ] || [ -z "$resource_group" ] || [ -z "$admin_password" ]; then
    echo "Skipping PostgreSQL AGE/data initialization (missing required values)."
    return
  fi

  if [ -z "$admin_user" ]; then
    admin_user="pgadmin"
  fi
  if [ -z "$graph_name" ]; then
    graph_name="customer_graph"
  fi

  echo "Configuring PostgreSQL server parameters for AGE..."
  az postgres flexible-server parameter set --resource-group "$resource_group" --server-name "$server_name" --name azure.extensions --value AGE >/dev/null
  az postgres flexible-server parameter set --resource-group "$resource_group" --server-name "$server_name" --name shared_preload_libraries --value age >/dev/null

  echo "Restarting PostgreSQL server..."
  az postgres flexible-server restart --resource-group "$resource_group" --name "$server_name" >/dev/null
  wait_postgres_ready "$resource_group" "$server_name"

  local script_dir
  script_dir="$(cd "$(dirname "$0")" && pwd)"
  local repo_root
  repo_root="$(cd "$script_dir/../.." && pwd)"

  local loader_script="$repo_root/postgresql_age/load_data/load_customer_graph.py"
  local data_dir="$repo_root/postgresql_age/data"
  local python_exe="python"
  if [ -x "$repo_root/.venv/bin/python" ]; then
    python_exe="$repo_root/.venv/bin/python"
  elif [ -x "$repo_root/.venv/Scripts/python.exe" ]; then
    python_exe="$repo_root/.venv/Scripts/python.exe"
  fi

  echo "Enabling AGE extension in postgres database..."
  age_init_succeeded=false
  for attempt in $(seq 1 15); do
    if PGHOST="$server_fqdn" \
      PGPORT="5432" \
      PGDATABASE="postgres" \
      PGUSER="$admin_user" \
      PGPASSWORD="$admin_password" \
      PGSSLMODE="require" \
      "$python_exe" - <<'PY'
import os
import psycopg

conn = psycopg.connect(
    host=os.environ['PGHOST'],
    port=int(os.environ.get('PGPORT', '5432')),
    dbname=os.environ.get('PGDATABASE', 'postgres'),
    user=os.environ['PGUSER'],
  password=os.environ['PGPASSWORD'],
  sslmode='require'
)
conn.autocommit = True
with conn.cursor() as cur:
    cur.execute("CREATE EXTENSION IF NOT EXISTS AGE CASCADE;")
    cur.execute("ALTER DATABASE postgres SET search_path = ag_catalog, \"$user\", public;")
conn.close()
PY
    then
      age_init_succeeded=true
      break
    fi

    echo "AGE extension initialization failed (attempt $attempt/15). Retrying in 12 seconds..."
    sleep 12
  done

  if [ "$age_init_succeeded" != "true" ]; then
    echo "ERROR: AGE extension initialization failed after retries."
    exit 1
  fi

  echo "Skipping graph data load (provisioning-only mode)."
}

invoke_provision_phase() {
  local phase_name="$1"
  local deploy_mcp="$2"
  local deploy_fastapi="$3"
  local deploy_webapp="$4"

  echo "=========================================="
  echo "Provision phase: $phase_name"
  echo "=========================================="

  set_azd_env "deployContainerApp" "false"
  set_azd_env "deployContainerAppsEnv" "true"
  set_azd_env "deployMcpServerContainerApp" "$deploy_mcp"
  set_azd_env "deployFastApiContainerApp" "$deploy_fastapi"
  set_azd_env "deployWebappContainerApp" "$deploy_webapp"

  azd provision --no-prompt
}

acr_name="$(get_azd_env acrName)"
acr_login_server="$(get_azd_env acrLoginServer)"
mcp_image_name="$(get_azd_env mcpServerImageName)"
mcp_image_tag="$(get_azd_env mcpServerImageTag)"
build_mcp="$(get_azd_env buildMcpServerContainer)"
fastapi_image_name="$(get_azd_env fastApiImageName)"
fastapi_image_tag="$(get_azd_env fastApiImageTag)"
build_fastapi="$(get_azd_env buildFastApiContainer)"
webapp_image_name="$(get_azd_env webappImageName)"
webapp_image_tag="$(get_azd_env webappImageTag)"
build_webapp="$(get_azd_env buildWebappContainer)"
resource_group="$(get_azd_env AZURE_RESOURCE_GROUP)"
postgres_server_name="$(get_azd_env postgresqlServerName)"
postgres_server_fqdn="$(get_azd_env postgresqlServerFqdn)"
postgres_admin_user="$(get_azd_env postgresqlAdminLogin)"
postgres_admin_password="$(get_azd_env POSTGRESQL_ADMIN_PASSWORD)"
graph_name="$(get_azd_env graphName)"

echo "Skipping PostgreSQL AGE initialization (provisioning-only mode)."

if [ -z "$acr_name" ]; then
  echo "ACR not deployed, skipping container builds"
  exit 0
fi

script_dir="$(cd "$(dirname "$0")" && pwd)"

if [ "$build_mcp" != "false" ]; then
  mcp_full_path="$(cd "$script_dir/$MCP_SERVER_PATH" && pwd)"
  IFS=';' read -r mcp_needed mcp_hash <<< "$(build_needed "$mcp_full_path" "mcpServerFolderHash")"
  if [ "$mcp_needed" = "true" ]; then
    az acr build --registry "$acr_name" --image "${mcp_image_name}:${mcp_image_tag}" --image "${mcp_image_name}:latest" --file "$mcp_full_path/Dockerfile" "$mcp_full_path"
    set_azd_env "mcpServerFolderHash" "$mcp_hash"
    echo "MCP Server container built: $acr_login_server/${mcp_image_name}:${mcp_image_tag}"
  fi
fi

if [ "$build_fastapi" != "false" ]; then
  fastapi_full_path="$(cd "$script_dir/$FASTAPI_PATH" && pwd)"
  IFS=';' read -r fastapi_needed fastapi_hash <<< "$(build_needed "$fastapi_full_path" "fastApiFolderHash")"
  if [ "$fastapi_needed" = "true" ]; then
    az acr build --registry "$acr_name" --image "${fastapi_image_name}:${fastapi_image_tag}" --image "${fastapi_image_name}:latest" --file "$fastapi_full_path/Dockerfile" "$fastapi_full_path"
    set_azd_env "fastApiFolderHash" "$fastapi_hash"
    echo "FastAPI container built: $acr_login_server/${fastapi_image_name}:${fastapi_image_tag}"
  fi
fi

if [ "$build_webapp" != "false" ]; then
  webapp_full_path="$(cd "$script_dir/$WEBAPP_PATH" && pwd)"
  IFS=';' read -r webapp_needed webapp_hash <<< "$(build_needed "$webapp_full_path" "webappFolderHash")"
  if [ "$webapp_needed" = "true" ]; then
    fastapi_fqdn="$(get_azd_env fastApiContainerAppFqdn)"
    if [ -n "$fastapi_fqdn" ]; then
      az acr build --registry "$acr_name" --image "${webapp_image_name}:${webapp_image_tag}" --image "${webapp_image_name}:latest" --build-arg "VITE_API_BASE_URL=https://${fastapi_fqdn}" --file "$webapp_full_path/Dockerfile" "$webapp_full_path"
    else
      az acr build --registry "$acr_name" --image "${webapp_image_name}:${webapp_image_tag}" --image "${webapp_image_name}:latest" --file "$webapp_full_path/Dockerfile" "$webapp_full_path"
    fi
    set_azd_env "webappFolderHash" "$webapp_hash"
    echo "Webapp container built: $acr_login_server/${webapp_image_name}:${webapp_image_tag}"
  fi
fi

invoke_provision_phase "MCP Server" "true" "false" "false"
invoke_provision_phase "FastAPI Backend" "true" "true" "false"
invoke_provision_phase "Webapp" "true" "true" "true"

echo "=========================================="
echo "Post-provision completed successfully."
echo "=========================================="