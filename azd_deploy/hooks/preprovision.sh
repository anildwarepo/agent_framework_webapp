#!/bin/bash
#
# Pre-provision hook to get the client IP address for PostgreSQL firewall rule.
#

echo "=========================================="
echo "Pre-provision hook: Getting client IP..."
echo "=========================================="

# Get client public IP
clientIp=$(curl -s --max-time 10 https://api.ipify.org 2>/dev/null || echo "")

if [ -n "$clientIp" ]; then
    echo "Client IP: $clientIp"
    
    # Set it as an azd environment variable
    azd env set CLIENT_IP_ADDRESS "$clientIp"
    echo "CLIENT_IP_ADDRESS set to: $clientIp"
else
    echo "WARNING: Could not get client IP address. PostgreSQL firewall rule will not be created."
    # Set empty value
    azd env set CLIENT_IP_ADDRESS ""
fi

echo "=========================================="
