#!/usr/bin/env bash
# Deploys the perfume agent MVP to Azure Container Apps. Safe to re-run.
#
#   export AZURE_OPENAI_ENDPOINT=https://<res>.openai.azure.com
#   export AZURE_OPENAI_API_KEY=...            # secret
#   export AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-4o-mini
#   infra/deploy.sh
#
# Image source (pick one):
#   IMAGE=ghcr.io/srivatsam/perfume-agent:<tag>   use a prebuilt image (the GitHub workflow sets this)
#   (unset, DEPLOY_ACR unset)                     default: ghcr.io/srivatsam/perfume-agent:latest
#   DEPLOY_ACR=true (IMAGE unset)                 create an ACR, build there with `az acr build`, pull via
#                                                 managed identity + AcrPull (needs role-assignment rights)
# Private ghcr.io package: export GHCR_PULL_TOKEN=<PAT with read:packages> (GHCR_USERNAME defaults to srivatsam).
#
# Optional: AZ_SUBSCRIPTION (defaults to the logged-in subscription), AZ_LOCATION (uaenorth),
#           RG (rg-perfume-agent-mvp), BASE_NAME (perfumeagent), AZURE_OPENAI_EMBED_DEPLOYMENT,
#           AZURE_OPENAI_IMAGE_DEPLOYMENT, AZURE_OPENAI_API_VERSION (2024-10-21), ADMIN_TOKEN (reused from the
#           running app, else generated), BRAND_FILTER, DEFAULT_LANG (en), IMAGE_TAG (git short sha),
#           DEPLOY_SCOPE (subscription | group; see infra/README.md).
set -euo pipefail

cd "$(dirname "$0")/.."

AZ_SUBSCRIPTION="${AZ_SUBSCRIPTION:-}"
AZ_LOCATION="${AZ_LOCATION:-uaenorth}"
RG="${RG:-rg-perfume-agent-mvp}"
BASE_NAME="${BASE_NAME:-perfumeagent}"
DEPLOY_SCOPE="${DEPLOY_SCOPE:-subscription}"
DEPLOY_ACR="${DEPLOY_ACR:-false}"
IMAGE="${IMAGE:-}"
GHCR_IMAGE_REPO="${GHCR_IMAGE_REPO:-ghcr.io/srivatsam/perfume-agent}"
GHCR_USERNAME="${GHCR_USERNAME:-srivatsam}"
GHCR_PULL_TOKEN="${GHCR_PULL_TOKEN:-}"
AZURE_OPENAI_API_VERSION="${AZURE_OPENAI_API_VERSION:-2024-10-21}"
AZURE_OPENAI_EMBED_DEPLOYMENT="${AZURE_OPENAI_EMBED_DEPLOYMENT:-}"
AZURE_OPENAI_IMAGE_DEPLOYMENT="${AZURE_OPENAI_IMAGE_DEPLOYMENT:-}"
BRAND_FILTER="${BRAND_FILTER:-}"
DEFAULT_LANG="${DEFAULT_LANG:-en}"
ADMIN_TOKEN="${ADMIN_TOKEN:-}"
IMAGE_TAG="${IMAGE_TAG:-$(git rev-parse --short HEAD 2>/dev/null || date -u +%Y%m%d%H%M%S)}"
PLACEHOLDER_IMAGE="mcr.microsoft.com/k8se/quickstart:latest"
ACR_IMAGE_REPO="perfume-agent"
TAGS_JSON='{"project":"perfume-agent-mvp","environment":"disposable","owner":"srivatsam","expires":"2026-10-05","managed-by":"bicep","repo":"srivatsam/careem-design-companion"}'

die() { echo "ERROR: $*" >&2; exit 1; }
log() { echo; echo "==> $*"; }

for v in AZURE_OPENAI_ENDPOINT AZURE_OPENAI_API_KEY AZURE_OPENAI_CHAT_DEPLOYMENT; do
  [[ -n "${!v:-}" ]] || die "$v is required (export it before running)."
done
[[ "$DEPLOY_SCOPE" == "subscription" || "$DEPLOY_SCOPE" == "group" ]] || die "DEPLOY_SCOPE must be subscription or group"
[[ "$DEPLOY_ACR" == "true" || "$DEPLOY_ACR" == "false" ]] || die "DEPLOY_ACR must be true or false"
command -v python3 >/dev/null || die "python3 is required (used to write the temporary parameters file)."

if [[ -z "$IMAGE" && "$DEPLOY_ACR" != "true" ]]; then
  IMAGE="${GHCR_IMAGE_REPO}:latest"
fi

# ---- login ------------------------------------------------------------------
if ! az account show --only-show-errors >/dev/null 2>&1; then
  die "Not logged in to Azure. Run 'az login' (and optionally export AZ_SUBSCRIPTION=<id>) and retry."
fi
# Without AZ_SUBSCRIPTION, use whatever the login selected (azure/login with AZURE_CREDENTIALS sets it).
if [[ -n "$AZ_SUBSCRIPTION" ]]; then
  az account set --subscription "$AZ_SUBSCRIPTION"
fi
echo "Subscription: $(az account show --query '[name, id]' -o tsv | paste -sd ' ')"
echo "Resource group: $RG ($AZ_LOCATION), scope: $DEPLOY_SCOPE, ACR: $DEPLOY_ACR, image: ${IMAGE:-<built in ACR>}"

# ---- step 0: resource providers ----------------------------------------------
log "Step 0: ensuring resource providers are registered"
providers=(Microsoft.App Microsoft.OperationalInsights Microsoft.Storage)
[[ "$DEPLOY_ACR" == "true" ]] && providers+=(Microsoft.ContainerRegistry Microsoft.ManagedIdentity)
for ns in "${providers[@]}"; do
  state="$(az provider show --namespace "$ns" --query registrationState -o tsv 2>/dev/null || echo Unknown)"
  if [[ "$state" != "Registered" ]]; then
    echo "registering $ns (was: $state)"
    az provider register --namespace "$ns" --wait --only-show-errors \
      || echo "WARNING: could not register $ns; ask a subscription Owner to run: az provider register --namespace $ns" >&2
  fi
done

# ---- helpers ----------------------------------------------------------------
PARAMS_FILE="$(mktemp)"
trap 'rm -f "$PARAMS_FILE"' EXIT
chmod 600 "$PARAMS_FILE"

REGISTRY_SERVER=""
REGISTRY_USERNAME=""
REGISTRY_PASSWORD=""
if [[ "$DEPLOY_ACR" != "true" && -n "$GHCR_PULL_TOKEN" ]]; then
  REGISTRY_SERVER="${IMAGE%%/*}"
  REGISTRY_USERNAME="$GHCR_USERNAME"
  REGISTRY_PASSWORD="$GHCR_PULL_TOKEN"
fi

# Writes the ARM parameters file (secrets go to a 0600 temp file, never onto the command line).
write_params() {
  local image="$1" suffix="$2"
  P_IMAGE="$image" P_SUFFIX="$suffix" P_SCOPE="$DEPLOY_SCOPE" P_LOCATION="$AZ_LOCATION" P_RG="$RG" \
  P_TAGS="$TAGS_JSON" P_BASE_NAME="$BASE_NAME" P_ADMIN_TOKEN="$ADMIN_TOKEN" P_DEPLOY_ACR="$DEPLOY_ACR" \
  P_REG_SERVER="$REGISTRY_SERVER" P_REG_USER="$REGISTRY_USERNAME" P_REG_PASSWORD="$REGISTRY_PASSWORD" \
  P_API_VERSION="$AZURE_OPENAI_API_VERSION" P_EMBED="$AZURE_OPENAI_EMBED_DEPLOYMENT" \
  P_IMAGE_DEPLOYMENT="$AZURE_OPENAI_IMAGE_DEPLOYMENT" P_BRAND="$BRAND_FILTER" P_LANG="$DEFAULT_LANG" \
  python3 - "$PARAMS_FILE" <<'PY'
import json, os, sys
e = os.environ
p = {
    "location": e["P_LOCATION"],
    "baseName": e["P_BASE_NAME"],
    "tags": json.loads(e["P_TAGS"]),
    "deployAcr": e["P_DEPLOY_ACR"] == "true",
    "registryServer": e["P_REG_SERVER"],
    "registryUsername": e["P_REG_USER"],
    "registryPassword": e["P_REG_PASSWORD"],
    "containerImage": e["P_IMAGE"],
    "azureOpenAiEndpoint": e["AZURE_OPENAI_ENDPOINT"],
    "azureOpenAiChatDeployment": e["AZURE_OPENAI_CHAT_DEPLOYMENT"],
    "azureOpenAiEmbedDeployment": e["P_EMBED"],
    "azureOpenAiImageDeployment": e["P_IMAGE_DEPLOYMENT"],
    "azureOpenAiApiVersion": e["P_API_VERSION"],
    "azureOpenAiApiKey": e["AZURE_OPENAI_API_KEY"],
    "adminToken": e["P_ADMIN_TOKEN"],
    "brandFilter": e["P_BRAND"],
    "defaultLang": e["P_LANG"],
    "revisionSuffix": e["P_SUFFIX"],
}
if e["P_SCOPE"] == "subscription":
    p["resourceGroupName"] = e["P_RG"]
doc = {
    "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#",
    "contentVersion": "1.0.0.0",
    "parameters": {k: {"value": v} for k, v in p.items()},
}
with open(sys.argv[1], "w") as f:
    json.dump(doc, f)
PY
}

# Runs the deployment; prints the outputs JSON on stdout.
deploy() {
  local name="$1"
  if [[ "$DEPLOY_SCOPE" == "subscription" ]]; then
    az deployment sub create \
      --name "$name" \
      --location "$AZ_LOCATION" \
      --template-file infra/main.bicep \
      --parameters "@$PARAMS_FILE" \
      --query properties.outputs -o json --only-show-errors
  else
    az group show --name "$RG" >/dev/null 2>&1 \
      || die "DEPLOY_SCOPE=group needs the resource group $RG to exist already (see infra/README.md)."
    az deployment group create \
      --name "$name" \
      --resource-group "$RG" \
      --template-file infra/resources.bicep \
      --parameters "@$PARAMS_FILE" \
      --query properties.outputs -o json --only-show-errors
  fi
}

output() { python3 -c 'import json,sys; print(json.load(sys.stdin)[sys.argv[1]]["value"])' "$1"; }

# ---- admin token: reuse the running app's secret on re-runs ------------------
GENERATED_TOKEN=0
if [[ -z "$ADMIN_TOKEN" ]]; then
  ADMIN_TOKEN="$(az containerapp secret show --name "ca-${BASE_NAME}" --resource-group "$RG" \
    --secret-name admin-token --query value -o tsv 2>/dev/null || true)"
  if [[ -z "$ADMIN_TOKEN" ]]; then
    ADMIN_TOKEN="$(openssl rand -hex 24)"
    GENERATED_TOKEN=1
  fi
fi
if [[ "${GITHUB_ACTIONS:-}" == "true" ]]; then
  echo "::add-mask::$ADMIN_TOKEN"
  [[ -n "$GHCR_PULL_TOKEN" ]] && echo "::add-mask::$GHCR_PULL_TOKEN"
fi

# ---- ACR path only: bootstrap the registry and build the image in Azure -------
if [[ -z "$IMAGE" ]]; then
  ACR_NAME=""
  if az group show --name "$RG" >/dev/null 2>&1; then
    ACR_NAME="$(az acr list --resource-group "$RG" --query '[0].name' -o tsv 2>/dev/null || true)"
  fi
  if [[ -z "$ACR_NAME" ]]; then
    log "Step 1: creating resource group, registry, storage, environment (placeholder image)"
    write_params "$PLACEHOLDER_IMAGE" ""
    OUT="$(deploy "perfume-agent-mvp-bootstrap-${AZ_LOCATION}")"
    ACR_NAME="$(output acrName <<<"$OUT")"
  else
    log "Step 1: skipped (registry $ACR_NAME already exists; step 3 reconciles all infrastructure)"
  fi
  ACR_LOGIN_SERVER="$(az acr show --name "$ACR_NAME" --query loginServer -o tsv)"
  IMAGE="${ACR_LOGIN_SERVER}/${ACR_IMAGE_REPO}:${IMAGE_TAG}"

  if az acr repository show-tags --name "$ACR_NAME" --repository "$ACR_IMAGE_REPO" -o tsv 2>/dev/null | grep -qx "$IMAGE_TAG"; then
    log "Step 2: image $IMAGE already exists; skipping build"
  else
    log "Step 2: building $IMAGE with ACR Tasks (the build runs in Azure, not locally)"
    az acr build --registry "$ACR_NAME" --image "${ACR_IMAGE_REPO}:${IMAGE_TAG}" --file Dockerfile . --only-show-errors
  fi
else
  log "Steps 1-2: skipped (using prebuilt image $IMAGE)"
fi

# ---- step 3: deploy the image --------------------------------------------------
# Revision suffix from the image tag: lowercase letters/digits/hyphens, starts with a letter, unique per deploy.
TAG_PART="${IMAGE##*/}"; TAG_PART="${TAG_PART%%@*}"
[[ "$TAG_PART" == *:* ]] && TAG_PART="${TAG_PART##*:}" || TAG_PART="latest"
SAFE_TAG="$(echo "$TAG_PART" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9-' '-' | cut -c1-16 | sed 's/-*$//')"
REVISION_SUFFIX="v${SAFE_TAG}-$(date -u +%m%d%H%M%S)"
log "Step 3: deploying $IMAGE (revision suffix $REVISION_SUFFIX)"
write_params "$IMAGE" "$REVISION_SUFFIX"
OUT="$(deploy "perfume-agent-mvp-app-${AZ_LOCATION}")"
FQDN="$(output containerAppFqdn <<<"$OUT")"
APP_NAME="$(output containerAppName <<<"$OUT")"

echo
echo "Deployed: https://${FQDN}"
echo "Container app: $APP_NAME   Image: $IMAGE"
echo "Health:   curl -fsS https://${FQDN}/api/health"
echo "Admin:    curl -fsS -H \"Authorization: Bearer \$ADMIN_TOKEN\" https://${FQDN}/api/admin/summary"
echo "First request after idle may take ~10-30 s (scale from zero; first boot also imports the catalogue)."
if [[ "$GENERATED_TOKEN" == "1" ]]; then
  echo
  echo "Generated ADMIN_TOKEN (shown once; also stored as the container app secret 'admin-token'):"
  echo "  $ADMIN_TOKEN"
fi
