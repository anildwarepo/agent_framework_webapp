<#
.SYNOPSIS
    Pre-provision hook to get the client IP address for PostgreSQL firewall rule.
#>

Write-Host "=========================================="
Write-Host "Pre-provision hook: Getting client IP..."
Write-Host "=========================================="

# Get client public IP
try {
    $clientIp = (Invoke-WebRequest -Uri "https://api.ipify.org" -UseBasicParsing -TimeoutSec 10).Content.Trim()
    Write-Host "Client IP: $clientIp"
    
    # Set it as an azd environment variable
    cmd /c "azd env set CLIENT_IP_ADDRESS $clientIp 2>&1"
    Write-Host "CLIENT_IP_ADDRESS set to: $clientIp"
} catch {
    Write-Host "WARNING: Could not get client IP address. PostgreSQL firewall rule will not be created."
    Write-Host "Error: $_"
    # Set empty value
    cmd /c "azd env set CLIENT_IP_ADDRESS '' 2>&1"
}

Write-Host "=========================================="
