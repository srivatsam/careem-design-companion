// All MVP resources, deployed into the single tagged resource group created by main.bicep.
targetScope = 'resourceGroup'

param location string
param baseName string
param tags object
param containerImage string
param azureOpenAiEndpoint string
param azureOpenAiChatDeployment string
param azureOpenAiEmbedDeployment string
param azureOpenAiImageDeployment string = ''
param azureOpenAiApiVersion string
@secure()
param azureOpenAiApiKey string
@secure()
param adminToken string
param brandFilter string
param defaultLang string
@description('Create an Azure Container Registry and pull from it with a user-assigned identity (AcrPull). Needs role-assignment rights. Default: pull from an external registry such as ghcr.io.')
param deployAcr bool = false
@description('External registry server for a private image, e.g. ghcr.io. Empty (with deployAcr false) means anonymous pull of a public image.')
param registryServer string = ''
@description('External registry username, e.g. the GitHub user owning the package.')
param registryUsername string = ''
@secure()
@description('External registry password/token, e.g. a GitHub PAT with read:packages. Empty means anonymous pull.')
param registryPassword string = ''
@description('Revision suffix (lowercase letters, digits, hyphens; starts with a letter). Empty lets Container Apps generate one.')
@maxLength(30)
param revisionSuffix string = ''

var suffix = uniqueString(resourceGroup().id)
var acrName = take('acr${replace(baseName, '-', '')}${suffix}', 50)
var storageName = take('st${take(replace(baseName, '-', ''), 9)}${suffix}', 24)
var shareName = 'appdata'
var envStorageName = 'appdata'
var containerAppName = take('ca-${baseName}', 32)
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'
var appPort = 8000

// The public quickstart placeholder listens on 80 and has no /api/health; the real image listens on 8000.
var isPlaceholderImage = startsWith(containerImage, 'mcr.microsoft.com/k8se/quickstart')
var ingressPort = isPlaceholderImage ? 80 : appPort
var useRegistryCredential = !deployAcr && !empty(registryServer) && !empty(registryUsername) && !empty(registryPassword)

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${baseName}'
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = if (deployAcr) {
  name: acrName
  location: location
  tags: tags
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    supportsHttpsTrafficOnly: true
    // Container Apps mounts Azure Files over SMB with the account key.
    allowSharedKeyAccess: true
  }
}

resource fileService 'Microsoft.Storage/storageAccounts/fileServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource share 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-05-01' = {
  parent: fileService
  name: shareName
  properties: {
    shareQuota: 5
    enabledProtocols: 'SMB'
  }
}

resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-${baseName}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

resource envStorage 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  parent: env
  name: envStorageName
  properties: {
    azureFile: {
      accountName: storage.name
      accountKey: storage.listKeys().keys[0].value
      shareName: share.name
      accessMode: 'ReadWrite'
    }
  }
}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = if (deployAcr) {
  name: 'id-${baseName}'
  location: location
  tags: tags
}

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (deployAcr) {
  name: guid(acr.id, identity.id, acrPullRoleId)
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId: identity!.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

var baseEnv = [
  { name: 'LLM_PROVIDER', value: 'azure' }
  { name: 'AZURE_OPENAI_ENDPOINT', value: azureOpenAiEndpoint }
  { name: 'AZURE_OPENAI_API_KEY', secretRef: 'azure-openai-api-key' }
  { name: 'AZURE_OPENAI_API_VERSION', value: azureOpenAiApiVersion }
  { name: 'AZURE_OPENAI_CHAT_DEPLOYMENT', value: azureOpenAiChatDeployment }
  { name: 'DATABASE_PATH', value: '/data/app.db' }
  { name: 'DEFAULT_LANG', value: defaultLang }
  { name: 'ADMIN_TOKEN', secretRef: 'admin-token' }
  { name: 'RATE_LIMIT_PER_MINUTE', value: '30' }
  { name: 'PORT', value: string(appPort) }
  { name: 'IMAGE_CACHE_DIR', value: '/data/images' }
]
var optionalEnv = concat(
  empty(azureOpenAiEmbedDeployment) ? [] : [{ name: 'AZURE_OPENAI_EMBED_DEPLOYMENT', value: azureOpenAiEmbedDeployment }],
  empty(azureOpenAiImageDeployment) ? [] : [{ name: 'AZURE_OPENAI_IMAGE_DEPLOYMENT', value: azureOpenAiImageDeployment }],
  empty(brandFilter) ? [] : [{ name: 'BRAND_FILTER', value: brandFilter }]
)

// Probes only for the real image. The startup probe allows ~10 minutes for the first-boot catalogue import.
var appProbes = [
  {
    type: 'Startup'
    httpGet: { path: '/api/health', port: appPort }
    initialDelaySeconds: 10
    periodSeconds: 60
    failureThreshold: 10
    timeoutSeconds: 5
  }
  {
    type: 'Liveness'
    httpGet: { path: '/api/health', port: appPort }
    periodSeconds: 30
    failureThreshold: 3
    timeoutSeconds: 5
  }
  {
    type: 'Readiness'
    httpGet: { path: '/api/health', port: appPort }
    periodSeconds: 10
    failureThreshold: 3
    timeoutSeconds: 5
  }
]

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: containerAppName
  location: location
  tags: tags
  identity: deployAcr
    ? {
        type: 'UserAssigned'
        userAssignedIdentities: {
          '${identity.id}': {}
        }
      }
    : {
        type: 'None'
      }
  properties: {
    managedEnvironmentId: env.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: ingressPort
        transport: 'auto'
        allowInsecure: false
      }
      // ACR via managed identity (opt-in), a private external registry via password, or none (public image).
      registries: deployAcr
        ? [
            {
              server: acr!.properties.loginServer
              identity: identity.id
            }
          ]
        : useRegistryCredential
            ? [
                {
                  server: registryServer
                  username: registryUsername
                  passwordSecretRef: 'registry-password'
                }
              ]
            : []
      secrets: concat(
        [
          {
            name: 'azure-openai-api-key'
            value: azureOpenAiApiKey
          }
          {
            name: 'admin-token'
            value: adminToken
          }
        ],
        useRegistryCredential ? [{ name: 'registry-password', value: registryPassword }] : []
      )
    }
    template: {
      revisionSuffix: empty(revisionSuffix) ? null : revisionSuffix
      containers: [
        {
          name: 'app'
          image: containerImage
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: concat(baseEnv, optionalEnv)
          probes: isPlaceholderImage ? [] : appProbes
          volumeMounts: [
            {
              volumeName: 'appdata'
              mountPath: '/data'
            }
          ]
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 1
      }
      volumes: [
        {
          name: 'appdata'
          storageType: 'AzureFile'
          storageName: envStorage.name
          // uid/gid match the non-root user in the Dockerfile; nobrl avoids SMB byte-range lock errors with SQLite.
          mountOptions: 'uid=1000,gid=1000,dir_mode=0777,file_mode=0777,mfsymlinks,nobrl'
        }
      ]
    }
  }
  dependsOn: [
    acrPull
  ]
}

output containerAppFqdn string = app.properties.configuration.ingress.fqdn
output containerAppName string = app.name
output acrLoginServer string = deployAcr ? acr!.properties.loginServer : ''
output acrName string = deployAcr ? acr.name : ''
output identityId string = deployAcr ? identity.id : ''
output identityPrincipalId string = deployAcr ? identity!.properties.principalId : ''
output identityClientId string = deployAcr ? identity!.properties.clientId : ''
