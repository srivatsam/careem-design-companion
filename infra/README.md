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
- Azure Container Registry, **Standard** SKU, admin user disabled, **anonymous pull enabled**, zone redundancy off
  (`deployAcr=true`, the default)
- Storage account (Standard_LRS, TLS 1.2, no public blob access) with file share `appdata` (5 GB)
- Container Apps environment (consumption) with the share registered as storage `appdata` (SMB, ReadWrite)
- Container App `ca-perfumeagent`: external HTTPS-only ingress on 8000, 0-1 replicas, 0.5 vCPU / 1 GiB,
  `/data` mounted from the share (SQLite at `/data/app.db`, image cache at `/data/images`), single revision mode,
  a new revision per deploy (suffix derived from the image tag). No registry credentials: it pulls anonymously.

No managed identity and no role assignments, so the deploying identity needs only **Contributor**.
The only subscription-scope object is the resource group itself. Nothing touches any other group.

## Image source

**Default: Azure Container Registry in the same group, anonymous pull.** `deploy.sh` (and the deploy workflow):

1. On the first run, deploys everything with the public placeholder `mcr.microsoft.com/k8se/quickstart:latest`, so
   the registry exists before any image does.
2. Runs `az acr update --anonymous-pull-enabled true` (Bicep already sets it; this is a safety net).
3. Runs `az acr build --registry <acr> --image perfume-agent:<git short sha> .`. The build runs **in Azure** (ACR
   Tasks), so no local Docker is needed. It uploads the working tree minus `.dockerignore`, so a Kaggle CSV in
   `data/raw/` is baked into the image. The build is skipped if the tag already exists.
4. Deploys `<acr>.azurecr.io/perfume-agent:<tag>`. The app pulls without credentials.

Anonymous pull is registry-wide: **anyone who knows the login server can pull the image**, including the app code
(public on GitHub anyway) and any Kaggle CSV baked into it. That is acceptable for this disposable MVP. If it is not,
use the ghcr.io option with a private package and `GHCR_PULL_TOKEN`. Some subscription types (free trial) block
ACR Tasks; use the ghcr.io option there too.

**Override: any prebuilt image** (`IMAGE=...`, no ACR; `deployAcr=false`). The deploy workflow's manual run with
`registry=ghcr` builds on the GitHub runner, pushes `ghcr.io/srivatsam/perfume-agent:<sha>` and `:latest` with
`GITHUB_TOKEN`, and deploys it:

- **Public package:** after the first push, GitHub > Packages > `perfume-agent` > Package settings > Change
  visibility > Public, done once. GitHub has no REST API for this.
- **Private package:** set `GHCR_PULL_TOKEN` (classic PAT with only `read:packages`). The app then uses registry
  `ghcr.io`, user `srivatsam` and that token (Container App secret `registry-password`).

## Prerequisites

- Azure CLI 2.60+ (`az version`); Bicep comes with it (`az bicep install` if missing)
- `python3` and `openssl` (used by `deploy.sh`)
- An Azure OpenAI resource with a chat deployment (for example `gpt-4o-mini`); optionally an embedding
  deployment (`text-embedding-3-small`) and an image deployment

## Permissions and one-time setup

The deploying identity needs **Contributor on the subscription** and nothing else. That covers creating the group,
the deployment, registering resource providers, `az acr build` and `az acr update`.

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
for ns in Microsoft.App Microsoft.OperationalInsights Microsoft.Storage Microsoft.ContainerRegistry; do az provider register --namespace $ns --wait; done
az group create --name $RG --location uaenorth --tags \
  project=perfume-agent-mvp environment=disposable owner=srivatsam expires=2026-10-05 \
  managed-by=bicep repo=srivatsam/careem-design-companion
az ad sp create-for-rbac --name sp-perfume-agent-mvp --role Contributor \
  --scopes $(az group show --name $RG --query id -o tsv) --sdk-auth
```

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
| `GHCR_PULL_TOKEN` | no | ghcr option only: PAT with `read:packages` if the package stays private |
| `AZURE_OPENAI_EMBED_DEPLOYMENT` | no | blank disables semantic scoring |
| `AZURE_OPENAI_IMAGE_DEPLOYMENT` | no | image-generation deployment |
| `ADMIN_TOKEN` | no | protects `/api/admin/*`; if unset the running app's token is reused, else one is generated (masked in logs) |
| `KAGGLE_USERNAME`, `KAGGLE_KEY` | no | lets the workflow bake the Kaggle catalogue into the image |
| `AZURE_SUBSCRIPTION_ID` | no | overrides the subscription from the login; required only for OIDC |
| `AZURE_CLIENT_ID`, `AZURE_TENANT_ID` | no | only for the OIDC alternative |

`GITHUB_TOKEN` (automatic) pushes the image for the ghcr option. Optional repository variables: `BRAND_FILTER`, `DEPLOY_SCOPE`
(`group` for the least-privilege variant).

## Deploy from a laptop

```bash
az login
export AZ_SUBSCRIPTION=<subscription-id>        # optional; defaults to the logged-in one
export AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com
export AZURE_OPENAI_API_KEY=<key>
export AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-4o-mini
export AZURE_OPENAI_EMBED_DEPLOYMENT=text-embedding-3-small   # optional

# Default: build in the group's ACR. Or override with a prebuilt image:
# export IMAGE=ghcr.io/srivatsam/perfume-agent:<sha>
# export GHCR_PULL_TOKEN=<pat>                   # if that package is private

infra/deploy.sh
```

`deploy.sh` is safe to re-run:

0. Registers the resource providers it needs (a warning if it lacks the rights).
1. ACR path: if the registry does not exist yet, deploys everything with the placeholder image.
2. ACR path: enables anonymous pull, then `az acr build` builds the Dockerfile **in Azure** (skipped if the tag exists).
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

- ACR Standard: about **0.67 / day** (~20 / month), billed while the registry exists. This is most of the bill.
  ACR Tasks builds add a few cents each.
- Container Apps (consumption, scale to zero): usually **0**. The monthly free grant (180k vCPU-s, 360k GiB-s,
  2M requests) covers light MVP use.
- Storage (file share, a few MB used): **cents**.
- Log Analytics: first 5 GB / month ingestion is free per billing account; a small app stays under **1**.
- ghcr.io option instead of ACR: free for public packages, total well under 1 / week.

One week with the default setup costs about 5 USD. Deleting the group stops all charges.

## Known caveats

- SQLite runs on an SMB share. The volume is mounted with `nobrl` (SMB byte-range locks break SQLite) and uid/gid
  1000 (the image's non-root user). The app opens the DB in WAL mode. WAL keeps a shared-memory `-shm` file, which
  is not reliable on network file systems. With one replica and one process it normally works. If you see
  `database is locked` or `disk I/O error`, switch the app to `journal_mode=DELETE` for this path.
  `maxReplicas` stays at 1 for this reason.
- Scale to zero means the first request after ~5 idle minutes waits for a cold start (~10 to 30 s).
