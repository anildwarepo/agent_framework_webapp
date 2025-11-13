# run.ps1

$ErrorActionPreference = "Stop"

# Always run from this script's directory
Set-Location $PSScriptRoot

# ---- Python env / deps ----
uv sync          # install/update deps, creates .venv if needed

# In PowerShell the activation script is Activate.ps1, not "activate"
. ".\.venv\Scripts\Activate.ps1"

# ---- MCP Server ----
Write-Host "Starting Weather MCP server on :3000 ..."
Start-Process powershell -WorkingDirectory (Join-Path $PSScriptRoot 'mcp_server') -ArgumentList @(
    '-NoExit',
    '-Command',
    'python af_weather_mcp_server.py'
)


Write-Host "Starting Search MCP server on :3001 ..."
Start-Process powershell -WorkingDirectory (Join-Path $PSScriptRoot 'mcp_server') -ArgumentList @(
    '-NoExit',
    '-Command',
    'python af_alta_search_mcp_server.py'
)

Write-Host "Starting AGE MCP server on :3002 ..."
Start-Process powershell -WorkingDirectory (Join-Path $PSScriptRoot 'mcp_server') -ArgumentList @(
    '-NoExit',
    '-Command',
    'python age_mcp_server.py'
)

# ---- FastAPI + PostgreSQL + AGE ----
Write-Host "Starting FastAPI on :8080 ..."
Start-Process powershell -WorkingDirectory (Join-Path $PSScriptRoot 'af_fastapi') -ArgumentList @(
    '-NoExit',
    '-Command',
    'uvicorn af_fastapi:app --port 8080 --reload'
)

# ---- React Frontend ----
Write-Host "Starting React dev server ..."
Start-Process powershell -WorkingDirectory (Join-Path $PSScriptRoot 'webapp') -ArgumentList @(
    '-NoExit',
    '-Command',
    'npm install; npm run dev'
)

Write-Host ""
Write-Host "All services have been launched in separate PowerShell windows."
