param(
    [ValidateSet("up", "down", "restart", "logs", "ps")]
    [string]$Action = "up",

    [switch]$Build,
    [switch]$Detached,
    [string]$Service
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$composeFile = "docker-compose.yml"
$envFile = ".env.docker"
$sampleFile = ".env.docker.sample"

if (-not (Test-Path $composeFile)) {
    throw "Missing $composeFile in $PSScriptRoot"
}

if (-not (Test-Path $envFile)) {
    if (Test-Path $sampleFile) {
        Copy-Item $sampleFile $envFile
        Write-Host "Created $envFile from $sampleFile."
    }
    else {
        throw "Missing $envFile and $sampleFile."
    }
    Write-Host "Fill required values in $envFile (PostgreSQL + Entra SP) before running 'up'."
    if ($Action -eq "up" -or $Action -eq "restart") {
        exit 1
    }
}

$composeBase = @("compose", "--env-file", $envFile, "-f", $composeFile)

switch ($Action) {
    "up" {
        Write-Host "Bringing down existing stack first..."
        & docker @($composeBase + @("down", "--remove-orphans"))

        $args = $composeBase + @("up", "-d", "--build")
        if ($Service) { $args += $Service }
        & docker @args
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

        if ($Detached -or $Service) {
            Write-Host "Stack is running. Use '.\deploy-docker-desktop.ps1 -Action logs' to stream logs."
        }
    }
    "down" {
        & docker @($composeBase + @("down", "--remove-orphans"))
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    "restart" {
        & docker @($composeBase + @("down", "--remove-orphans"))
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        $upArgs = $composeBase + @("up", "-d", "--build")
        if ($Service) { $upArgs += $Service }
        & docker @upArgs
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        Write-Host "Stack restarted."
    }
    "logs" {
        $logArgs = $composeBase + @("logs", "-f", "--tail", "200")
        if ($Service) { $logArgs += $Service }
        & docker @logArgs
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    "ps" {
        & docker @($composeBase + @("ps"))
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
}
