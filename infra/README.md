# Azure deployment (disposable MVP)

Everything lives in **one resource group** (`rg-perfume-agent-mvp`, default region `uaenorth`) and is
removed by deleting that group. Every resource and the group itself carry these tags:

| tag | value |
|---|---|
| project | perfume-agent-mvp |
| environment | disposable |
| owner | srivatsam |
| expires | 2026-10-05 |
| managed-by | bicep |
| repo | srivatsam/careem-design-companion |

What gets created (`main.bicep` -> `resources.bicep`):

- Log Analytics workspace (PerGB2018, 30-day retention)
- Storage account (Standard_LRS, TLS 1.2, no public blob access) with file share `appdata` (5 GB)
- Container Apps environment (consumption) with the share registered as storage `appdata` (SMB, ReadWrite)
- Container App `ca-perfumeagent`: external HTTPS-only ingress on 8000, 0-1 replicas, 0.5 vCPU / 1 GiB,
  `/data` mounted from the share (SQLite at `/data/app.db`, image cache at `/data/images`), single revision mode,
  a new revision per deploy (suffix derived from the image tag)
- Only with `deployAcr=true` (opt-in): Azure Container Registry (Basic, admin user disabled) and a user-assigned
  managed identity with **AcrPull** on it

The only subscription-scope object is the resource group itself. Nothing touches any other group.

## Image source

**Default: GitHub Container Registry.** The deploy workflow builds the Dockerfile on the GitHub runner and pushes
`ghcr.io/srivatsam/perfume-agent:<short sha>` and `:latest` using `GITHUB_TOKEN`. The Container App then pulls it:

- **Public package (recommended, the repo is public anyway):** after the first workflow run, open
  GitHub > your profile > Packages > `perfume-agent` > Package settings > Change visibility > Public. Do this once.
  GitHub has no REST API for changing package visibility. The app then pulls anonymously; no registry credential
  is stored anywhere.
- **Private package:** create a classic PAT with only `read:packages` and store it as the `GHCR_PULL_TOKEN` secret.
  `deploy.sh` then configures the Container App registry `ghcr.io` with user `srivatsam` and that token (secret
  `registry-password`).

Until the package is public or `GHCR_PULL_TOKEN` is set, the new revision fails to pull and the app will not start.

**Opt-in: Azure Container Registry** (`DEPLOY_ACR=true`, `IMAGE` unset). `deploy.sh` first deploys with the public
placeholder `mcr.microsoft.com/k8se/quickstart:latest` to create the registry, builds in Azure with `az acr build`
(ACR Tasks, no local Docker), then deploys the real image, pulled with the managed identity. This path creates a
role assignment, so the deploying identity also needs User Access Administrator (or Owner) on the resource group.

## Prerequisites

- Azure CLI 2.60+ (`az version`); Bicep comes with it (`az bicep install` if missing)
- `python3` and `openssl` (used by `deploy.sh`)
- An Azure OpenAI resource with a chat deployment (for example `gpt-4o-mini`); optionally an embedding
  deployment (`text-embedding-3-small`) and an image deployment

## Permissions and one-time setup

With the default ghcr.io image source the deploying identity needs **Contributor on the subscription** and nothing
else. That covers creating the group, the deployment, and registering resource providers.

```bash
SUB=$(az account show --query id -o tsv)

az ad sp create-for-rbac --name sp-perfume-agent-mvp --role Contributor \
  --scopes /subscriptions/$SUB --sdk-auth > azure-credentials.json
# Paste the whole JSON into the AZURE_CREDENTIALS secret, then delete the file.
```

The JSON carries the subscription id, so `AZURE_SUBSCRIPTION_ID` is not needed with this login.

**Least-privilege variant (Contributor on the group only).** An Owner pre-creates the tagged group and registers
the providers once. The service principal gets Contributor scoped to the group, and you set the repository variable
`DEPLOY_SCOPE=group`. `deploy.sh` then runs `az deployment group create` against `resources.bicep`, because a
subscription-scope deployment needs subscription rights. `main.bicep`'s group creation is not used; running it
anyway would only be a no-op tag update.

```bash
RG=rg-perfume-agent-mvp
for ns in Microsoft.App Microsoft.OperationalInsights Microsoft.Storage; do az provider register --namespace $ns --wait; done
az group create --name $RG --location uaenorth --tags \
  project=perfume-agent-mvp environment=disposable owner=srivatsam expires=2026-10-05 \
  managed-by=bicep repo=srivatsam/careem-design-companion
az ad sp create-for-rbac --name sp-perfume-agent-mvp --role Contributor \
  --scopes $(az group show --name $RG --query id -o tsv) --sdk-auth
```

For the ACR opt-in, also run
`az role assignment create --assignee-object-id <sp object id> --assignee-principal-type ServicePrincipal --role "User Access Administrator" --scope <group id>`
and register `Microsoft.ContainerRegistry` and `Microsoft.ManagedIdentity`.

<details>
<summary>Alternative login: OIDC (no stored Azure secret)</summary>

Used by the workflows only when `AZURE_CREDENTIALS` is **not** set. Needs `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`,
`AZURE_SUBSCRIPTION_ID`.

```bash
APP_ID=$(az ad app create --display-name sp-perfume-agent-mvp-oidc --query appId -o tsv)
SP_ID=$(az ad sp create --id $APP_ID --query id -o tsv)
az ad app federated-credential create --id $APP_ID --parameters '{
  "name": "gh-dreamy-faraday",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:srivatsam/careem-design-companion:ref:refs/heads/claude/dreamy-faraday-3vhoig",
  "audiences": ["api://AzureADTokenExchange"]}'
# The scheduled teardown runs from the default branch; replace main if yours differs
az ad app federated-credential create --id $APP_ID --parameters '{
  "name": "gh-default-branch",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:srivatsam/careem-design-companion:ref:refs/heads/main",
  "audiences": ["api://AzureADTokenExchange"]}'
az role assignment create --assignee-object-id $SP_ID --assignee-principal-type ServicePrincipal \
  --role Contributor --scope /subscriptions/$SUB
echo "AZURE_CLIENT_ID=$APP_ID AZURE_TENANT_ID=$(az account show --query tenantId -o tsv) AZURE_SUBSCRIPTION_ID=$SUB"
```
</details>

## GitHub secrets

| secret | required | notes |
|---|---|---|
| `AZURE_CREDENTIALS` | **yes** | JSON from `az ad sp create-for-rbac --sdk-auth`; also selects the subscription |
| `AZURE_OPENAI_ENDPOINT` | **yes** | `https://<resource>.openai.azure.com` |
| `AZURE_OPENAI_API_KEY` | **yes** | stored in the app as secret `azure-openai-api-key` |
| `AZURE_OPENAI_CHAT_DEPLOYMENT` | **yes** | e.g. `gpt-4o-mini` |
| `GHCR_PULL_TOKEN` | no | PAT with `read:packages`; only if the ghcr.io package stays private |
| `AZURE_OPENAI_EMBED_DEPLOYMENT` | no | blank disables semantic scoring |
| `AZURE_OPENAI_IMAGE_DEPLOYMENT` | no | image-generation deployment |
| `ADMIN_TOKEN` | no | protects `/api/admin/*`; if unset the running app's token is reused, else one is generated (masked in logs) |
| `KAGGLE_USERNAME`, `KAGGLE_KEY` | no | lets the workflow bake the Kaggle catalogue into the image |
| `AZURE_SUBSCRIPTION_ID` | no | overrides the subscription from the login; required only for OIDC |
| `AZURE_CLIENT_ID`, `AZURE_TENANT_ID` | no | only for the OIDC alternative |

`GITHUB_TOKEN` (automatic) pushes the image. Optional repository variables: `BRAND_FILTER`, `DEPLOY_SCOPE`
(`group` for the least-privilege variant).

## Deploy from a laptop

```bash
az login
export AZ_SUBSCRIPTION=<subscription-id>        # optional; defaults to the logged-in one
export AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com
export AZURE_OPENAI_API_KEY=<key>
export AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-4o-mini
export AZURE_OPENAI_EMBED_DEPLOYMENT=text-embedding-3-small   # optional

# Image: any of
export IMAGE=ghcr.io/srivatsam/perfume-agent:<sha>   # a tag the workflow pushed (default: :latest)
# export GHCR_PULL_TOKEN=<pat>                       # if the package is private
# export DEPLOY_ACR=true; unset IMAGE                # build in your own ACR instead (needs role-assignment rights)

infra/deploy.sh
```

`deploy.sh` is safe to re-run:

0. Registers the resource providers it needs (a warning if it lacks the rights).
1. ACR path only: if the registry does not exist yet, deploys everything with the placeholder image.
2. ACR path only: `az acr build` builds the Dockerfile **in Azure** (skipped if the tag exists). Some subscription
   types (free trial) block ACR Tasks.
3. Deploys the image with a new revision suffix, then prints the URL and an admin curl.

Deployment names are fixed (`perfume-agent-mvp-app-<region>`, plus `...-bootstrap-<region>` on the ACR path), so the
history does not grow. The Azure CLI has no `--tags` flag for `az deployment sub create`, so the deployment records
themselves are not tagged. The group and every resource are.

First boot imports the seed catalogue (plus any `data/raw/*.csv` baked into the image) into `/data/app.db` on
the file share. Later restarts and new revisions find the rows and skip the import. To force a re-import, delete
`app.db` from the `appdata` share.

## Status

```bash
infra/status.sh      # URL, image, revisions, replica count, health, last 50 log lines
curl -fsS -H "Authorization: Bearer $ADMIN_TOKEN" https://<fqdn>/api/admin/summary
```

## Tear down

```bash
infra/teardown.sh          # shows what will be deleted, asks you to type the group name
infra/teardown.sh --yes    # non-interactive
```

The script refuses unless the group is tagged `project=perfume-agent-mvp` **and** `environment=disposable`, then runs
`az group delete --yes --no-wait`. It deletes nothing else and purges nothing. The ghcr.io package is not in Azure;
delete it from GitHub Packages if you want it gone.

`.github/workflows/teardown.yml` runs the same script on demand and on `0 3 6 10 *` (06 Oct, 03:00 UTC, the day
after the `expires` tag). GitHub **only runs scheduled workflows from the default branch**, so merge it there for
the schedule to fire. Cron has no year field, so it fires every 6 October until the workflow is removed.

## Cost (rough, USD)

- Container Apps (consumption, scale to zero): usually **0**. The monthly free grant (180k vCPU-s, 360k GiB-s,
  2M requests) covers light MVP use.
- ghcr.io: free for public packages.
- Storage (file share, a few MB used): **cents**.
- Log Analytics: first 5 GB / month ingestion is free per billing account; a small app stays under **1**.
- ACR opt-in only: Basic is about **5 / month** (~0.17 / day), plus a few cents per ACR Tasks build.

One week with the default setup costs well under 1 USD (about 1 to 2 USD with ACR). Deleting the group stops all
charges.

## Known caveats

- SQLite runs on an SMB share. The volume is mounted with `nobrl` (SMB byte-range locks break SQLite) and uid/gid
  1000 (the image's non-root user). The app opens the DB in WAL mode. WAL keeps a shared-memory `-shm` file, which
  is not reliable on network file systems. With one replica and one process it normally works. If you see
  `database is locked` or `disk I/O error`, switch the app to `journal_mode=DELETE` for this path.
  `maxReplicas` stays at 1 for this reason.
- Scale to zero means the first request after ~5 idle minutes waits for a cold start (~10 to 30 s).
