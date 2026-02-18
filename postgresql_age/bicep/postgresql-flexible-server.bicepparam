using './postgresql-flexible-server.bicep'

// Required parameters
param serverName = 'anildwapgv16withage' // Provide a unique name when deploying
param administratorLogin = 'anildwa'
param administratorLoginPassword = '' // Set this value when deploying

// Optional parameters with defaults
param location = 'westus'
param postgresqlVersion = '16'
param skuName = 'Standard_D4ds_v5'
param skuTier = 'GeneralPurpose'
param storageSizeGB = 32
param backupRetentionDays = 7
param geoRedundantBackup = false
param highAvailabilityEnabled = false
param tags = {
  environment: 'development'
  application: 'knowledge-graph'
  purpose: 'apache-age'
}
