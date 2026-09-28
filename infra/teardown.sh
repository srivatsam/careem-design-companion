#!/usr/bin/env bash
# Deletes the MVP resource group, and only if it carries project=perfume-agent-mvp AND environment=disposable.
# Nothing else is deleted or purged.
#   infra/teardown.sh           # asks you to type the resource group name
#   infra/teardown.sh --yes     # non-interactive (CI)
set -euo pipefail

RG="${RG:-rg-perfume-agent-mvp}"
ASSUME_YES=0
for arg in "$@"; do
  case "$arg" in
    -y|--yes) ASSUME_YES=1 ;;
    -h|--help) sed -n '2,6p' "$0"; exit 0 ;;
    *) echo "Unknown argument: $arg" >&2; exit 2 ;;
  esac
done

if ! az account show --only-show-errors >/dev/null 2>&1; then
  echo "Not logged in to Azure. Run 'az login' first." >&2
  exit 1
fi
[[ -n "${AZ_SUBSCRIPTION:-}" ]] && az account set --subscription "$AZ_SUBSCRIPTION"

if [[ "$(az group exists --name "$RG")" != "true" ]]; then
  echo "Resource group $RG does not exist; nothing to delete."
  exit 0
fi

project="$(az group show --name "$RG" --query 'tags.project' -o tsv)"
environment="$(az group show --name "$RG" --query 'tags.environment' -o tsv)"
if [[ "$project" != "perfume-agent-mvp" || "$environment" != "disposable" ]]; then
  echo "REFUSING: $RG is not tagged project=perfume-agent-mvp and environment=disposable" >&2
  echo "  (found project='$project' environment='$environment')." >&2
  exit 1
fi

echo "About to delete resource group $RG in subscription $(az account show --query name -o tsv)."
echo "Tags: $(az group show --name "$RG" --query tags -o json | tr -d '\n ')"
echo "Resources that will be deleted:"
az resource list --resource-group "$RG" --query '[].{name:name, type:type}' -o table

if [[ "$ASSUME_YES" != "1" ]]; then
  read -r -p "Type the resource group name ($RG) to confirm: " answer
  [[ "$answer" == "$RG" ]] || { echo "Confirmation did not match; aborting."; exit 1; }
fi

az group delete --name "$RG" --yes --no-wait
echo "Deletion of $RG started (runs in the background; check with: az group exists --name $RG)."
