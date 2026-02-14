using './main.bicep'

// ── Required: Set these to match your provisioned resources ─────────────────

param environmentName = 'spagent'

// Azure OpenAI
param azureOpenaiEndpoint     = 'https://demo-openai-lab02.openai.azure.com'
param azureOpenaiDeployment   = 'gpt-4o'
param azureOpenaiEmbeddingDeployment = 'text-embedding-3-small'
param azureOpenaiApiVersion   = '2024-06-01'
param azureOpenaiApiKey       = readEnvironmentVariable('AZURE_OPENAI_API_KEY', '')

// Azure AI Search
param azureSearchEndpoint     = 'https://aisearchlab002.search.windows.net'
param azureSearchIndexName    = 'sharepoint-docs-index'
param searchApproach          = 'indexer'
param azureSearchApiKey       = readEnvironmentVariable('AZURE_SEARCH_API_KEY', '')
param azureSearchApiVersion   = '2025-11-01-preview'
param knowledgeBaseName       = 'sharepoint-indexed-kb'
param knowledgeSourceName     = 'sharepoint-indexed-ks'

// Azure Cosmos DB
param cosmosEndpoint          = 'https://cosmos-xc4icdh2gdp6.documents.azure.com:443/'
param cosmosDatabase          = 'sharepoint-agent'
param cosmosContainer         = 'conversations'

// Microsoft Entra ID
param entraTenantId           = 'cc4fb710-2bb6-4c47-ace3-a3c85b8fdf4c'
param entraClientId           = '806458c7-d269-46d6-90a5-3db2d1df16b4'

// Resource IDs for RBAC — left empty because resources are in other RGs.
// API keys are used instead. Assign RBAC manually if switching to managed identity.
param azureOpenaiResourceId   = ''
param azureSearchResourceId   = ''
param cosmosResourceId        = ''

// ── Optional: Tune as needed ────────────────────────────────────────────────

param location                = 'eastus2'
param imageTag                = 'latest'
param logLevel                = 'INFO'
param maxInputLength          = '4000'
param rateLimitPerMinute      = '20'
