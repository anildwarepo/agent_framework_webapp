<#
.SYNOPSIS
    Post-provision hook to initialize PostgreSQL AGE, build containers, and deploy apps in sequence.
#>

param(
    [string]$McpServerPath = "../../mcp_server",
    [string]$FastApiPath = "../../af_fastapi",
    [string]$WebappPath = "../../webapp"
)

$ErrorActionPreference = "Stop"

Write-Host "=========================================="
Write-Host "Post-provision hook starting..."
Write-Host "=========================================="

function Get-AzdEnvValue {
    param([string]$Name)
    (cmd /c "azd env get-value $Name 2>nul").Trim()
}

function Set-AzdEnvValue {
    param(
        [string]$Name,
        [string]$Value
    )
    cmd /c "azd env set $Name $Value 2>&1" | Out-Null
}

function Get-FolderHash {
    param([string]$FolderPath)

    $files = Get-ChildItem -Path $FolderPath -Recurse -File |
        Where-Object { $_.FullName -notmatch '(__pycache__|node_modules|\.git|\.(pyc|pyo|egg-info))' } |
        Sort-Object FullName

    $hashInput = ""
    foreach ($file in $files) {
        $relativePath = $file.FullName.Substring($FolderPath.Length)
        $fileHash = (Get-FileHash -Path $file.FullName -Algorithm MD5).Hash
        $hashInput += "$relativePath`:$fileHash`n"
    }

    $bytes = [System.Text.Encoding]::UTF8.GetBytes($hashInput)
    $md5 = [System.Security.Cryptography.MD5]::Create()
    $hashBytes = $md5.ComputeHash($bytes)
    [BitConverter]::ToString($hashBytes) -replace '-', ''
}

function Test-BuildNeeded {
    param(
        [string]$FolderPath,
        [string]$HashEnvVarName
    )

    $currentHash = Get-FolderHash -FolderPath $FolderPath
    $storedHash = Get-AzdEnvValue $HashEnvVarName

    if ($currentHash -eq $storedHash) {
        return @{ Needed = $false; Hash = $currentHash }
    }

    return @{ Needed = $true; Hash = $currentHash }
}

function Save-FolderHash {
    param(
        [string]$HashEnvVarName,
        [string]$Hash
    )
    Set-AzdEnvValue -Name $HashEnvVarName -Value $Hash
}

function Invoke-AcrBuild {
    param(
        [string]$RegistryName,
        [string]$SourcePath,
        [string]$ImageName,
        [string]$ImageTag,
        [string]$Label,
        [string[]]$BuildArgs = @()
    )

    Push-Location $SourcePath
    $buildArgsString = ""
    foreach ($arg in $BuildArgs) {
        $buildArgsString += " --build-arg $arg"
    }

    $cmd = "az acr build --registry $RegistryName --image `"${ImageName}:${ImageTag}`" --image `"${ImageName}:latest`" --file Dockerfile . --no-logs --query runId -o tsv$buildArgsString"
    $runId = Invoke-Expression $cmd
    $buildExitCode = $LASTEXITCODE
    Pop-Location

    if ($buildExitCode -ne 0 -or [string]::IsNullOrEmpty($runId)) {
        throw "ACR build failed for $Label"
    }

    $safeLabel = $Label -replace '[^a-zA-Z0-9_-]', '_'
    $logFile = Join-Path $env:TEMP "${safeLabel}-acr-build-${runId}.log"
    cmd /c "az acr task logs --registry $RegistryName --run-id $runId > \"$logFile\" 2>&1"
    if (Test-Path $logFile) {
        Get-Content $logFile
    }
}

function Wait-PostgresqlReady {
    param(
        [string]$ResourceGroup,
        [string]$ServerName,
        [int]$MaxAttempts = 60,
        [int]$DelaySeconds = 10
    )

    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        $state = az postgres flexible-server show --resource-group $ResourceGroup --name $ServerName --query "state" -o tsv 2>$null
        if ($LASTEXITCODE -eq 0 -and $state -eq "Ready") {
            return
        }

        Write-Host "Waiting for PostgreSQL server to be Ready (attempt $attempt/$MaxAttempts, current state: $state)..."
        Start-Sleep -Seconds $DelaySeconds
    }

    throw "PostgreSQL server did not reach Ready state in time."
}

function Ensure-PostgresqlAllowAllIps {
    param(
        [string]$ResourceGroup,
        [string]$ServerName
    )

    if ([string]::IsNullOrEmpty($ResourceGroup) -or [string]::IsNullOrEmpty($ServerName)) {
        return
    }

    Write-Host "Opening PostgreSQL firewall to all IPs for data loading..."
    az postgres flexible-server firewall-rule create --resource-group $ResourceGroup --name $ServerName --rule-name "AllowAllIps" --start-ip-address "0.0.0.0" --end-ip-address "255.255.255.255" | Out-Null
}

function Invoke-WithRetry {
    param(
        [scriptblock]$Action,
        [string]$Operation,
        [int]$MaxAttempts = 12,
        [int]$DelaySeconds = 10
    )

    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        try {
            & $Action
            return
        }
        catch {
            if ($attempt -eq $MaxAttempts) {
                throw "${Operation} failed after ${MaxAttempts} attempts. Last error: $($_.Exception.Message)"
            }

            Write-Host "${Operation} failed (attempt $attempt/$MaxAttempts). Retrying in $DelaySeconds seconds..."
            Start-Sleep -Seconds $DelaySeconds
        }
    }
}

function Initialize-PostgresqlAgeAndData {
    param(
        [string]$ResourceGroup,
        [string]$ServerName,
        [string]$AdminUser,
        [string]$AdminPassword,
        [string]$ServerFqdn,
        [string]$GraphName
    )

    if ([string]::IsNullOrEmpty($ServerName) -or [string]::IsNullOrEmpty($ResourceGroup) -or [string]::IsNullOrEmpty($AdminPassword)) {
        Write-Host "Skipping PostgreSQL AGE/data initialization (missing required values)."
        return
    }

    $effectiveAdminUser = if (-not [string]::IsNullOrEmpty($AdminUser)) { $AdminUser } else { "pgadmin" }
    $effectiveGraphName = if (-not [string]::IsNullOrEmpty($GraphName)) { $GraphName } else { "customer_graph" }

    Write-Host "Configuring PostgreSQL server parameters for AGE..."
    az postgres flexible-server parameter set --resource-group $ResourceGroup --server-name $ServerName --name azure.extensions --value AGE | Out-Null
    az postgres flexible-server parameter set --resource-group $ResourceGroup --server-name $ServerName --name shared_preload_libraries --value age | Out-Null

    Write-Host "Restarting PostgreSQL server..."
    az postgres flexible-server restart --resource-group $ResourceGroup --name $ServerName | Out-Null
    Wait-PostgresqlReady -ResourceGroup $ResourceGroup -ServerName $ServerName

    Write-Host "Enabling AGE extension in postgres database..."
    $scriptDir = $PSScriptRoot
    $repoRoot = Resolve-Path (Join-Path $scriptDir "../..")
    $loaderScript = Join-Path $repoRoot "postgresql_age/load_data/load_customer_graph.py"
    $dataDir = Join-Path $repoRoot "postgresql_age/data"
    $venvPython = Join-Path $repoRoot ".venv/Scripts/python.exe"
    $pythonExe = if (Test-Path $venvPython) { $venvPython } else { "python" }

    $initSqlScript = Join-Path $env:TEMP "init_age_${ServerName}.py"
    @"
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
"@ | Set-Content -Path $initSqlScript -Encoding UTF8

    Write-Host "Preparing PostgreSQL connection for AGE initialization..."
    $env:PGHOST = $ServerFqdn
    $env:PGPORT = "5432"
    $env:PGDATABASE = "postgres"
    $env:PGUSER = $effectiveAdminUser
    $env:PGPASSWORD = $AdminPassword
    $env:PGSSLMODE = "require"
    Invoke-WithRetry -Operation "AGE extension initialization" -Action {
        & $pythonExe $initSqlScript
        if ($LASTEXITCODE -ne 0) {
            throw "Init SQL script exited with code $LASTEXITCODE"
        }
    } -MaxAttempts 15 -DelaySeconds 12

    Write-Host "Skipping graph data load (provisioning-only mode)."

    Remove-Item -Path $initSqlScript -ErrorAction SilentlyContinue
}

function Invoke-ProvisionPhase {
    param(
        [string]$PhaseName,
        [string]$DeployMcp,
        [string]$DeployFastApi,
        [string]$DeployWebapp
    )

    Write-Host "=========================================="
    Write-Host "Provision phase: $PhaseName"
    Write-Host "=========================================="

    Set-AzdEnvValue -Name "deployContainerApp" -Value "false"
    Set-AzdEnvValue -Name "deployContainerAppsEnv" -Value "true"
    Set-AzdEnvValue -Name "deployMcpServerContainerApp" -Value $DeployMcp
    Set-AzdEnvValue -Name "deployFastApiContainerApp" -Value $DeployFastApi
    Set-AzdEnvValue -Name "deployWebappContainerApp" -Value $DeployWebapp

    cmd /c "azd provision --no-prompt 2>&1"
    if ($LASTEXITCODE -ne 0) {
        throw "Provision phase '$PhaseName' failed."
    }
}

$acrName = Get-AzdEnvValue "acrName"
$acrLoginServer = Get-AzdEnvValue "acrLoginServer"
$mcpServerImageName = Get-AzdEnvValue "mcpServerImageName"
$mcpServerImageTag = Get-AzdEnvValue "mcpServerImageTag"
$buildMcpServerContainer = Get-AzdEnvValue "buildMcpServerContainer"
$fastApiImageName = Get-AzdEnvValue "fastApiImageName"
$fastApiImageTag = Get-AzdEnvValue "fastApiImageTag"
$buildFastApiContainer = Get-AzdEnvValue "buildFastApiContainer"
$webappImageName = Get-AzdEnvValue "webappImageName"
$webappImageTag = Get-AzdEnvValue "webappImageTag"
$buildWebappContainer = Get-AzdEnvValue "buildWebappContainer"
$resourceGroup = Get-AzdEnvValue "AZURE_RESOURCE_GROUP"
$postgresqlServerName = Get-AzdEnvValue "postgresqlServerName"
$postgresqlServerFqdn = Get-AzdEnvValue "postgresqlServerFqdn"
$postgresqlAdminLogin = Get-AzdEnvValue "postgresqlAdminLogin"
$postgresqlAdminPassword = Get-AzdEnvValue "POSTGRESQL_ADMIN_PASSWORD"
$graphName = Get-AzdEnvValue "graphName"

if (-not [string]::IsNullOrEmpty($postgresqlServerName)) {
    Write-Host "Skipping PostgreSQL AGE initialization (provisioning-only mode)."
}

if ([string]::IsNullOrEmpty($acrName)) {
    Write-Host "ACR not deployed, skipping container builds"
    exit 0
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:AZURE_CORE_NO_COLOR = "1"
chcp 65001 | Out-Null

if ($buildMcpServerContainer -ne "false") {
    $mcpServerFullPath = Resolve-Path (Join-Path $scriptDir $McpServerPath)
    $mcpBuildCheck = Test-BuildNeeded -FolderPath $mcpServerFullPath -HashEnvVarName "mcpServerFolderHash"
    if ($mcpBuildCheck.Needed) {
        Invoke-AcrBuild -RegistryName $acrName -SourcePath $mcpServerFullPath -ImageName $mcpServerImageName -ImageTag $mcpServerImageTag -Label "mcp-server"
        Save-FolderHash -HashEnvVarName "mcpServerFolderHash" -Hash $mcpBuildCheck.Hash
        Write-Host "MCP Server container built: $acrLoginServer/${mcpServerImageName}:${mcpServerImageTag}"
    }
}

if ($buildFastApiContainer -ne "false") {
    $fastApiFullPath = Resolve-Path (Join-Path $scriptDir $FastApiPath)
    $fastApiBuildCheck = Test-BuildNeeded -FolderPath $fastApiFullPath -HashEnvVarName "fastApiFolderHash"
    if ($fastApiBuildCheck.Needed) {
        Invoke-AcrBuild -RegistryName $acrName -SourcePath $fastApiFullPath -ImageName $fastApiImageName -ImageTag $fastApiImageTag -Label "fastapi"
        Save-FolderHash -HashEnvVarName "fastApiFolderHash" -Hash $fastApiBuildCheck.Hash
        Write-Host "FastAPI container built: $acrLoginServer/${fastApiImageName}:${fastApiImageTag}"
    }
}

if ($buildWebappContainer -ne "false") {
    $webappFullPath = Resolve-Path (Join-Path $scriptDir $WebappPath)
    $webappBuildCheck = Test-BuildNeeded -FolderPath $webappFullPath -HashEnvVarName "webappFolderHash"
    if ($webappBuildCheck.Needed) {
        $fastApiFqdn = Get-AzdEnvValue "fastApiContainerAppFqdn"
        $buildArgs = @()
        if (-not [string]::IsNullOrEmpty($fastApiFqdn)) {
            $buildArgs += "VITE_API_BASE_URL=https://${fastApiFqdn}"
        }

        Invoke-AcrBuild -RegistryName $acrName -SourcePath $webappFullPath -ImageName $webappImageName -ImageTag $webappImageTag -Label "webapp" -BuildArgs $buildArgs
        Save-FolderHash -HashEnvVarName "webappFolderHash" -Hash $webappBuildCheck.Hash
        Write-Host "Webapp container built: $acrLoginServer/${webappImageName}:${webappImageTag}"
    }
}

Invoke-ProvisionPhase -PhaseName "MCP Server" -DeployMcp "true" -DeployFastApi "false" -DeployWebapp "false"
Invoke-ProvisionPhase -PhaseName "FastAPI Backend" -DeployMcp "true" -DeployFastApi "true" -DeployWebapp "false"
Invoke-ProvisionPhase -PhaseName "Webapp" -DeployMcp "true" -DeployFastApi "true" -DeployWebapp "true"

Write-Host "=========================================="
Write-Host "Post-provision completed successfully."
Write-Host "=========================================="