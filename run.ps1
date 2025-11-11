# run.ps1

$ErrorActionPreference = "Stop"

# Always run from this script's directory
Set-Location $PSScriptRoot

# ---- Python env / deps ----
uv sync          # install/update deps, creates .venv if needed

# In PowerShell the activation script is Activate.ps1, not "activate"
. ".\.venv\Scripts\Activate.ps1"

# ---- MCP Server ----
Write-Host "Starting MCP server on :3000 ..."
Start-Process powershell -WorkingDirectory (Join-Path $PSScriptRoot 'mcp_server') -ArgumentList @(
    '-NoExit',
    '-Command',
    'uvicorn mcp_fastapi_server:app --port 3000 --reload'
)

# ---- FastAPI + PostgreSQL + AGE ----
Write-Host "Starting FastAPI + PostgreSQL/AGE on :8080 ..."
Start-Process powershell -WorkingDirectory (Join-Path $PSScriptRoot 'postgresql_age_fastapi') -ArgumentList @(
    '-NoExit',
    '-Command',
    'uvicorn postgresql_age_fastapi:app --port 8080 --reload'
)

# ---- React Frontend ----
Write-Host "Starting React dev server ..."
Start-Process powershell -WorkingDirectory (Join-Path $PSScriptRoot 'knowledge_graph_app_frontend') -ArgumentList @(
    '-NoExit',
    '-Command',
    'npm install; npm run dev'
)

Write-Host ""
Write-Host "All services have been launched in separate PowerShell windows."
