// Perfume agent MVP: disposable, tagged, single-resource-group deployment.
// Tear down by deleting the resource group (infra/teardown.sh). Nothing here touches any other
// resource group; the only subscription-scope resource is the resource group itself.
targetScope = 'subscription'

@description('Azure region for the resource group and all resources. Container Apps is available in uaenorth.')
param location string = 'uaenorth'

@description('Name of the resource group that holds every resource of this MVP.')
param resourceGroupName string = 'rg-perfume-agent-mvp'

@description('Short lowercase base name used to derive resource names.')
@minLength(3)
@maxLength(12)
param baseName string = 'perfumeagent'

@description('Tags applied to the resource group and to every resource.')
param tags object = {
  project: 'perfume-agent-mvp'
  environment: 'disposable'
  owner: 'srivatsam'
  expires: '2026-10-05'
  'managed-by': 'bicep'
  repo: 'srivatsam/careem-design-companion'
}

@description('Create an Azure Container Registry pulled via managed identity + AcrPull (needs role-assignment rights). Default false: pull from ghcr.io.')
param deployAcr bool = false

@description('External registry server for a private image (e.g. ghcr.io). Leave empty for a public image.')
param registryServer string = ''

@description('External registry username (e.g. the GitHub user owning the package).')
param registryUsername string = ''

@description('External registry password (e.g. a GitHub PAT with read:packages). Leave empty for a public image.')
@secure()
param registryPassword string = ''

@description('Container image. The public placeholder lets the first deployment succeed before the real image is pushed to ACR.')
param containerImage string = 'mcr.microsoft.com/k8se/quickstart:latest'

@description('Azure OpenAI endpoint, e.g. https://<resource>.openai.azure.com')
param azureOpenAiEndpoint string

@description('Azure OpenAI chat model deployment name.')
param azureOpenAiChatDeployment string

@description('Azure OpenAI embedding deployment name (optional; empty disables semantic scoring).')
param azureOpenAiEmbedDeployment string = ''

@description('Azure OpenAI image-generation deployment name (optional).')
param azureOpenAiImageDeployment string = ''

@description('Azure OpenAI API version.')
param azureOpenAiApiVersion string = '2024-10-21'

@description('Azure OpenAI API key (stored as a Container Apps secret).')
@secure()
@minLength(1)
param azureOpenAiApiKey string

@description('Token protecting /api/admin/* (stored as a Container Apps secret).')
@secure()
@minLength(1)
param adminToken string

@description('Optional brand filter, e.g. "Ajmal".')
param brandFilter string = ''

@description('Revision suffix derived from the image tag so each deploy creates a new revision. Empty lets Container Apps pick one.')
@maxLength(30)
param revisionSuffix string = ''

@description('Default UI language (en | ar).')
@allowed([
  'en'
  'ar'
])
param defaultLang string = 'en'

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: resourceGroupName
  location: location
  tags: tags
}

module resources 'resources.bicep' = {
  name: 'perfume-agent-resources'
  scope: rg
  params: {
    location: location
    baseName: baseName
    tags: tags
    containerImage: containerImage
    azureOpenAiEndpoint: azureOpenAiEndpoint
    azureOpenAiChatDeployment: azureOpenAiChatDeployment
    azureOpenAiEmbedDeployment: azureOpenAiEmbedDeployment
    azureOpenAiImageDeployment: azureOpenAiImageDeployment
    azureOpenAiApiVersion: azureOpenAiApiVersion
    azureOpenAiApiKey: azureOpenAiApiKey
    adminToken: adminToken
    brandFilter: brandFilter
    defaultLang: defaultLang
    revisionSuffix: revisionSuffix
    deployAcr: deployAcr
    registryServer: registryServer
    registryUsername: registryUsername
    registryPassword: registryPassword
  }
}

output resourceGroupName string = rg.name
output containerAppFqdn string = resources.outputs.containerAppFqdn
output containerAppName string = resources.outputs.containerAppName
output acrLoginServer string = resources.outputs.acrLoginServer
output acrName string = resources.outputs.acrName
output identityId string = resources.outputs.identityId
output identityPrincipalId string = resources.outputs.identityPrincipalId
output identityClientId string = resources.outputs.identityClientId
