// ===========================================================================
// SharePoint Document Q&A Agent – Azure Container Apps Deployment
// ===========================================================================
// Deploys: ACR, Log Analytics, Container Apps Environment, Container App
// with system-assigned managed identity + RBAC for Azure OpenAI, AI Search,
// and Cosmos DB.
// ===========================================================================

targetScope = 'resourceGroup'

// ── Parameters ──────────────────────────────────────────────────────────────

@description('Environment name used as a prefix for all resources.')
param environmentName string

@description('Azure region for all resources.')
param location string = resourceGroup().location

@description('Container image tag. Defaults to latest.')
param imageTag string = 'latest'

// Existing resource endpoints (provisioned in Step 1)
@description('Azure OpenAI endpoint URL.')
param azureOpenaiEndpoint string

@description('Azure OpenAI chat deployment name.')
param azureOpenaiDeployment string = 'gpt-4o'

@description('Azure OpenAI embedding deployment name.')
param azureOpenaiEmbeddingDeployment string = 'text-embedding-3-small'

@description('Azure OpenAI API version.')
param azureOpenaiApiVersion string = '2024-06-01'

@description('Azure AI Search endpoint URL.')
param azureSearchEndpoint string

@description('Azure AI Search index name.')
param azureSearchIndexName string = 'sharepoint-docs-index'

@description('Search approach: indexer | foundryiq | indexed_sharepoint.')
param searchApproach string = 'indexer'

@description('Azure AI Search admin API key (for KB approaches or when RBAC is not available).')
@secure()
param azureSearchApiKey string = ''

@description('Azure OpenAI API key (when RBAC is not available, e.g. cross-RG).')
@secure()
param azureOpenaiApiKey string = ''

@description('Azure AI Search API version for KB retrieve calls.')
param azureSearchApiVersion string = '2025-11-01-preview'

@description('Knowledge Base name (for foundryiq / indexed_sharepoint).')
param knowledgeBaseName string = ''

@description('Knowledge Source name (for foundryiq / indexed_sharepoint).')
param knowledgeSourceName string = ''

@description('Azure Cosmos DB endpoint URL.')
param cosmosEndpoint string

@description('Cosmos DB database name.')
param cosmosDatabase string = 'sharepoint-agent'

@description('Cosmos DB container name.')
param cosmosContainer string = 'conversations'

@description('Microsoft Entra ID tenant ID.')
param entraTenantId string

@description('Microsoft Entra ID backend app client ID.')
param entraClientId string

@description('Log level for the application.')
param logLevel string = 'INFO'

@description('Maximum input length for user messages.')
param maxInputLength string = '4000'

@description('Rate limit per minute per user.')
param rateLimitPerMinute string = '20'

// Existing resource IDs for RBAC assignments (leave empty to skip — e.g. when using API keys or resources are in another RG)
@description('Resource ID of the Azure OpenAI account (for RBAC). Leave empty to skip.')
param azureOpenaiResourceId string = ''

@description('Resource ID of the Azure AI Search service (for RBAC). Leave empty to skip.')
param azureSearchResourceId string = ''

@description('Resource ID of the Azure Cosmos DB account (for RBAC). Leave empty to skip.')
param cosmosResourceId string = ''

// ── Variables ───────────────────────────────────────────────────────────────

var abbrs = {
  acr: 'cr'
  law: 'log'
  cae: 'cae'
  ca: 'ca'
}

var resourceToken = uniqueString(resourceGroup().id, environmentName)
var acrName = '${abbrs.acr}${replace(environmentName, '-', '')}${resourceToken}'
var lawName = '${abbrs.law}-${environmentName}'
var caeName = '${abbrs.cae}-${environmentName}'
var caName = '${abbrs.ca}-${environmentName}'
// Initial deploy uses a placeholder image; deploy script updates to the real ACR image after build
var containerImageRef = 'mcr.microsoft.com/k8se/quickstart:${imageTag}'

// Built-in role definition IDs
var cognitiveServicesOpenAIUserRoleId = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
var searchIndexDataReaderRoleId = '1407120a-92aa-4202-b7e9-c0e197c71c8f'
var cosmosDbDataContributorRoleId = '00000000-0000-0000-0000-000000000002'

// ── Azure Container Registry ────────────────────────────────────────────────

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: true
  }
  tags: {
    environment: environmentName
    app: 'sharepoint-agent'
  }
}

// ── Log Analytics Workspace ─────────────────────────────────────────────────

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: lawName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
  tags: {
    environment: environmentName
    app: 'sharepoint-agent'
  }
}

// ── Container Apps Environment ──────────────────────────────────────────────

resource containerAppsEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: caeName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
    zoneRedundant: false
  }
  tags: {
    environment: environmentName
    app: 'sharepoint-agent'
  }
}

// ── Container App ───────────────────────────────────────────────────────────

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: caName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: containerAppsEnv.id
    configuration: {
      registries: [
        {
          server: acr.properties.loginServer
          username: acrName
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: [
        {
          name: 'acr-password'
          value: acr.listCredentials().passwords[0].value
        }
        {
          name: 'search-api-key'
          value: azureSearchApiKey
        }
        {
          name: 'openai-api-key'
          value: azureOpenaiApiKey
        }
      ]
      ingress: {
        external: true
        targetPort: 8000
        allowInsecure: false
        transport: 'auto'
      }
    }
    template: {
      containers: [
        {
          name: 'sharepoint-agent'
          image: containerImageRef
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            { name: 'AZURE_OPENAI_ENDPOINT',              value: azureOpenaiEndpoint }
            { name: 'AZURE_OPENAI_DEPLOYMENT',             value: azureOpenaiDeployment }
            { name: 'AZURE_OPENAI_EMBEDDING_DEPLOYMENT',   value: azureOpenaiEmbeddingDeployment }
            { name: 'AZURE_OPENAI_API_VERSION',            value: azureOpenaiApiVersion }
            { name: 'AZURE_SEARCH_ENDPOINT',               value: azureSearchEndpoint }
            { name: 'AZURE_SEARCH_INDEX_NAME',             value: azureSearchIndexName }
            { name: 'SEARCH_APPROACH',                     value: searchApproach }
            { name: 'AZURE_SEARCH_API_KEY',                secretRef: 'search-api-key' }
            { name: 'AZURE_OPENAI_API_KEY',                secretRef: 'openai-api-key' }
            { name: 'AZURE_SEARCH_API_VERSION',            value: azureSearchApiVersion }
            { name: 'KNOWLEDGE_BASE_NAME',                 value: knowledgeBaseName }
            { name: 'KNOWLEDGE_SOURCE_NAME',               value: knowledgeSourceName }
            { name: 'COSMOS_ENDPOINT',                     value: cosmosEndpoint }
            { name: 'COSMOS_DATABASE',                     value: cosmosDatabase }
            { name: 'COSMOS_CONTAINER',                    value: cosmosContainer }
            { name: 'ENTRA_TENANT_ID',                     value: entraTenantId }
            { name: 'ENTRA_CLIENT_ID',                     value: entraClientId }
            { name: 'LOG_LEVEL',                           value: logLevel }
            { name: 'MAX_INPUT_LENGTH',                    value: maxInputLength }
            { name: 'RATE_LIMIT_PER_MINUTE',               value: rateLimitPerMinute }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/health'
                port: 8000
              }
              initialDelaySeconds: 30
              periodSeconds: 30
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/health'
                port: 8000
              }
              initialDelaySeconds: 15
              periodSeconds: 10
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 3
        rules: [
          {
            name: 'http-scaling'
            http: {
              metadata: {
                concurrentRequests: '20'
              }
            }
          }
        ]
      }
    }
  }
  tags: {
    environment: environmentName
    app: 'sharepoint-agent'
  }
}

// ── RBAC: Managed Identity → Azure OpenAI (Cognitive Services OpenAI User) ──
// Only assigned when azureOpenaiResourceId is provided (resources in the same RG)

resource openaiRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(azureOpenaiResourceId)) {
  name: guid(azureOpenaiResourceId, caName, cognitiveServicesOpenAIUserRoleId)
  scope: resourceGroup()
  properties: {
    principalId: containerApp.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesOpenAIUserRoleId)
  }
}

// ── RBAC: Managed Identity → AI Search (Search Index Data Reader) ───────────

resource searchRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(azureSearchResourceId)) {
  name: guid(azureSearchResourceId, caName, searchIndexDataReaderRoleId)
  scope: resourceGroup()
  properties: {
    principalId: containerApp.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', searchIndexDataReaderRoleId)
  }
}

// ── RBAC: Managed Identity → Cosmos DB (Cosmos DB Built-in Data Contributor)

resource cosmosRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(cosmosResourceId)) {
  name: guid(cosmosResourceId, caName, cosmosDbDataContributorRoleId)
  scope: resourceGroup()
  properties: {
    principalId: containerApp.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cosmosDbDataContributorRoleId)
  }
}

// ── Outputs ─────────────────────────────────────────────────────────────────

@description('The FQDN of the deployed Container App.')
output containerAppFqdn string = containerApp.properties.configuration.ingress.fqdn

@description('The name of the Container App.')
output containerAppName string = containerApp.name

@description('The ACR login server.')
output acrLoginServer string = acr.properties.loginServer

@description('The system-assigned managed identity principal ID.')
output managedIdentityPrincipalId string = containerApp.identity.principalId
