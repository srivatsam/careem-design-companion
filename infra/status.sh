#!/usr/bin/env bash
# Shows the app URL, active revision, replica count and the last 50 log lines.
set -euo pipefail

RG="${RG:-rg-perfume-agent-mvp}"
BASE_NAME="${BASE_NAME:-perfumeagent}"
APP="${APP_NAME:-ca-${BASE_NAME}}"

if ! az account show --only-show-errors >/dev/null 2>&1; then
  echo "Not logged in to Azure. Run 'az login' first." >&2
  exit 1
fi
[[ -n "${AZ_SUBSCRIPTION:-}" ]] && az account set --subscription "$AZ_SUBSCRIPTION"

FQDN="$(az containerapp show --name "$APP" --resource-group "$RG" --query properties.configuration.ingress.fqdn -o tsv)"
echo "URL:      https://${FQDN}"
echo "Image:    $(az containerapp show --name "$APP" --resource-group "$RG" --query 'properties.template.containers[0].image' -o tsv)"
echo "Tags:     $(az group show --name "$RG" --query tags -o json | tr -d '\n ')"
echo
echo "Revisions:"
az containerapp revision list --name "$APP" --resource-group "$RG" \
  --query '[].{name:name, active:properties.active, traffic:properties.trafficWeight, replicas:properties.replicas, health:properties.healthState, created:properties.createdTime}' \
  -o table
echo
echo "Replicas (0 means scaled to zero; the next request wakes it):"
az containerapp replica list --name "$APP" --resource-group "$RG" --query 'length(@)' -o tsv 2>/dev/null || echo 0
echo
echo "Health check:"
curl -fsS --max-time 60 "https://${FQDN}/api/health" || echo "(health check failed)"
echo
echo
echo "Last 50 log lines:"
az containerapp logs show --name "$APP" --resource-group "$RG" --tail 50 --format text 2>/dev/null \
  || echo "(no logs: the app is probably scaled to zero; use 'az containerapp logs show --type system' or Log Analytics)"
