# Azure PostgreSQL Flexible Server with Apache AGE Extension

This Bicep template provisions an Azure PostgreSQL Flexible Server version 16 with the Apache AGE (Graph Database) extension enabled.

## Resources Created

- **PostgreSQL Flexible Server** - Version 16 with configurable SKU
- **Server Parameters** - Configured for AGE extension:
  - `azure.extensions`: AGE
  - `shared_preload_libraries`: age
- **Firewall Rule** - Allows Azure services to access the server

## Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `serverName` | Name of the PostgreSQL server | (required) |
| `location` | Azure region | Resource group location |
| `administratorLogin` | Admin username | (required) |
| `administratorLoginPassword` | Admin password | (required) |
| `postgresqlVersion` | PostgreSQL version | `16` |
| `skuName` | SKU name | `Standard_B2s` |
| `skuTier` | SKU tier (Burstable/GeneralPurpose/MemoryOptimized) | `Burstable` |
| `storageSizeGB` | Storage size in GB | `32` |
| `backupRetentionDays` | Backup retention (7-35 days) | `7` |
| `geoRedundantBackup` | Enable geo-redundant backup | `false` |
| `highAvailabilityEnabled` | Enable high availability | `false` |
| `tags` | Resource tags | `{}` |

## Deployment

### Using Azure CLI

```bash
# Login to Azure
az login

# Create a resource group (if not exists)
az group create --name rg-knowledge-graph --location eastus

# Deploy using parameter file
az deployment group create \
  --resource-group rg-knowledge-graph \
  --template-file postgresql-flexible-server.bicep \
  --parameters postgresql-flexible-server.bicepparam \
  --parameters administratorLoginPassword='<your-secure-password>'

# Or deploy with inline parameters
az deployment group create \
  --resource-group rg-knowledge-graph \
  --template-file postgresql-flexible-server.bicep \
  --parameters serverName='pg-age-server' \
               administratorLogin='pgadmin' \
               administratorLoginPassword='<your-secure-password>'
```

### Using PowerShell

```powershell
# Login to Azure
Connect-AzAccount

# Create a resource group (if not exists)
New-AzResourceGroup -Name "rg-knowledge-graph" -Location "eastus"

# Deploy using parameter file
New-AzResourceGroupDeployment `
  -ResourceGroupName "rg-knowledge-graph" `
  -TemplateFile "postgresql-flexible-server.bicep" `
  -TemplateParameterFile "postgresql-flexible-server.bicepparam" `
  -administratorLoginPassword (ConvertTo-SecureString "<your-secure-password>" -AsPlainText -Force)
```

## Post-Deployment Steps

After the server is provisioned, connect to the database and create the AGE extension:

```sql
-- Create the AGE extension
CREATE EXTENSION IF NOT EXISTS age;

-- Load AGE
LOAD 'age';

-- Set the search path to include ag_catalog
SET search_path = ag_catalog, "$user", public;

-- Create a graph (example)
SELECT create_graph('my_graph');
```

## Important Notes

1. **Server Restart**: After the `shared_preload_libraries` parameter is set, the server will automatically restart to apply the changes.

2. **Firewall Rules**: The template creates a firewall rule to allow Azure services. You may need to add additional rules for your client IP addresses.

3. **Security**: 
   - Never commit passwords to source control
   - Use Azure Key Vault for production deployments
   - Consider using Azure AD authentication for enhanced security

4. **SKU Selection**: 
   - For development/testing: `Burstable` tier (Standard_B1ms, Standard_B2s)
   - For production: `GeneralPurpose` or `MemoryOptimized` tiers
