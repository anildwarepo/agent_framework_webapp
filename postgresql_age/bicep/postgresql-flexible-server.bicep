@description('The name of the PostgreSQL Flexible Server')
param serverName string

@description('Location for all resources')
param location string = resourceGroup().location

@description('The administrator login username for the PostgreSQL server')
param administratorLogin string

@description('The administrator login password for the PostgreSQL server')
@secure()
param administratorLoginPassword string

@description('PostgreSQL version')
@allowed([
  '16'
  '15'
  '14'
  '13'
])
param postgresqlVersion string = '16'

@description('The SKU name for the PostgreSQL Flexible Server')
param skuName string = 'Standard_B2s'

@description('The tier of the SKU')
@allowed([
  'Burstable'
  'GeneralPurpose'
  'MemoryOptimized'
])
param skuTier string = 'GeneralPurpose'

@description('Storage size in GB')
@minValue(32)
@maxValue(16384)
param storageSizeGB int = 32

@description('Backup retention days')
@minValue(7)
@maxValue(35)
param backupRetentionDays int = 7

@description('Enable geo-redundant backup')
param geoRedundantBackup bool = false

@description('Enable high availability')
param highAvailabilityEnabled bool = false

@description('Tags for the resources')
param tags object = {}

// PostgreSQL Flexible Server
resource postgresqlServer 'Microsoft.DBforPostgreSQL/flexibleServers@2023-12-01-preview' = {
  name: serverName
  location: location
  tags: tags
  sku: {
    name: skuName
    tier: skuTier
  }
  properties: {
    version: postgresqlVersion
    administratorLogin: administratorLogin
    administratorLoginPassword: administratorLoginPassword
    storage: {
      storageSizeGB: storageSizeGB
    }
    backup: {
      backupRetentionDays: backupRetentionDays
      geoRedundantBackup: geoRedundantBackup ? 'Enabled' : 'Disabled'
    }
    highAvailability: {
      mode: highAvailabilityEnabled ? 'ZoneRedundant' : 'Disabled'
    }
    authConfig: {
      activeDirectoryAuth: 'Disabled'
      passwordAuth: 'Enabled'
    }
  }
}

// Server Parameter: azure.extensions - Enable AGE extension
resource azureExtensions 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2023-12-01-preview' = {
  parent: postgresqlServer
  name: 'azure.extensions'
  properties: {
    value: 'AGE'
    source: 'user-override'
  }
}

// Server Parameter: shared_preload_libraries - Preload AGE library
resource sharedPreloadLibraries 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2023-12-01-preview' = {
  parent: postgresqlServer
  name: 'shared_preload_libraries'
  properties: {
    value: 'age'
    source: 'user-override'
  }
  dependsOn: [
    azureExtensions
  ]
}

// Firewall rule to allow Azure services
resource allowAzureServices 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2023-12-01-preview' = {
  parent: postgresqlServer
  name: 'AllowAllAzureServicesAndResourcesWithinAzureIps'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

// Outputs
@description('The fully qualified domain name of the PostgreSQL server')
output serverFqdn string = postgresqlServer.properties.fullyQualifiedDomainName

@description('The resource ID of the PostgreSQL server')
output serverId string = postgresqlServer.id

@description('The name of the PostgreSQL server')
output serverName string = postgresqlServer.name
