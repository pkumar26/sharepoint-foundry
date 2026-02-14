#!/usr/bin/env bash
# ===========================================================================
# deploy.sh – Build & deploy SharePoint Q&A Agent to Azure Container Apps
# ===========================================================================
# Usage:
#   ./scripts/deploy.sh -g <resource-group> -e <environment-name> [-t <image-tag>]
#
# Prerequisites:
#   • Azure CLI (az) installed & logged in
#   • Fill in infra/main.bicepparam with your resource values
# ===========================================================================

set -euo pipefail

# ── Defaults ─────────────────────────────────────────────────────────────────
RESOURCE_GROUP=""
ENV_NAME=""
IMAGE_TAG="latest"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── Parse args ───────────────────────────────────────────────────────────────
while getopts "g:e:t:" opt; do
  case $opt in
    g) RESOURCE_GROUP="$OPTARG" ;;
    e) ENV_NAME="$OPTARG" ;;
    t) IMAGE_TAG="$OPTARG" ;;
    *) echo "Usage: $0 -g <resource-group> -e <environment-name> [-t <image-tag>]" && exit 1 ;;
  esac
done

if [[ -z "$RESOURCE_GROUP" || -z "$ENV_NAME" ]]; then
  echo "Error: -g (resource group) and -e (environment name) are required."
  echo "Usage: $0 -g <resource-group> -e <environment-name> [-t <image-tag>]"
  exit 1
fi

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  SharePoint Q&A Agent – Container Apps Deployment       ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║  Resource Group : $RESOURCE_GROUP"
echo "║  Environment    : $ENV_NAME"
echo "║  Image Tag      : $IMAGE_TAG"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ── Step 1: Deploy infrastructure with Bicep ────────────────────────────────
echo "▸ [1/4] Deploying infrastructure via Bicep..."
az deployment group create \
  --resource-group "$RESOURCE_GROUP" \
  --name main \
  --template-file "$PROJECT_ROOT/infra/main.bicep" \
  --parameters "$PROJECT_ROOT/infra/main.bicepparam" \
  --parameters imageTag="$IMAGE_TAG" \
  --query "properties.outputs" \
  --output json

# Capture outputs from the main deployment
ACR_LOGIN_SERVER=$(az deployment group show \
  --resource-group "$RESOURCE_GROUP" \
  --name main \
  --query "properties.outputs.acrLoginServer.value" \
  --output tsv 2>/dev/null || echo "")

echo "  ACR Login Server: $ACR_LOGIN_SERVER"
echo ""

# ── Step 2: Build & push container image to ACR ─────────────────────────────
echo "▸ [2/4] Building & pushing container image to ACR..."
az acr build \
  --registry "${ACR_LOGIN_SERVER%%.*}" \
  --image "sharepoint-agent:$IMAGE_TAG" \
  --file "$PROJECT_ROOT/Dockerfile" \
  "$PROJECT_ROOT"

echo ""

# ── Step 3: Update Container App with the built image ───────────────────────
echo "▸ [3/4] Updating container app with built image..."
CA_NAME="ca-${ENV_NAME}"

# Force a new revision to pick up the built image
az containerapp update \
  --resource-group "$RESOURCE_GROUP" \
  --name "$CA_NAME" \
  --image "${ACR_LOGIN_SERVER}/sharepoint-agent:${IMAGE_TAG}" \
  --output none

echo ""

# ── Step 4: Verify deployment ────────────────────────────────────────────────
echo "▸ [4/4] Verifying deployment..."
FQDN=$(az containerapp show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$CA_NAME" \
  --query "properties.configuration.ingress.fqdn" \
  --output tsv)

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  ✅ Deployment complete!                                ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║  App URL  : https://$FQDN"
echo "║  Health   : https://$FQDN/health"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "Next steps:"
echo "  • Verify health: curl https://$FQDN/health"
echo "  • Check logs:    az containerapp logs show -g $RESOURCE_GROUP -n $CA_NAME --type console"
echo "  • Managed ID:    RBAC roles were auto-assigned to the system-assigned identity."
echo "                   No ENTRA_CLIENT_SECRET needed – DefaultAzureCredential handles auth."
