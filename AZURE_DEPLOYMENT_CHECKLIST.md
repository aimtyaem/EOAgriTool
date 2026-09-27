# Azure Deployment Checklist for EOAgriTool

Complete guide to configure and deploy EOAgriTool on Microsoft Azure.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Azure Resource Setup](#azure-resource-setup)
3. [Azure DevOps Pipeline Configuration](#azure-devops-pipeline-configuration)
4. [Environment Variables & Secrets](#environment-variables--secrets)
5. [Deployment Steps](#deployment-steps)
6. [Post-Deployment Verification](#post-deployment-verification)
7. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Software & Accounts

- **Azure Subscription** with active payment method
- **Azure CLI** (`az` command-line tool) installed locally
- **Azure DevOps** project (free tier available at [dev.azure.com](https://dev.azure.com))
- **Git** installed locally
- **GitHub Account** with access to the EOAgriTool repository
- **Python 3.12+** (for local testing)

### Install Azure CLI

```bash
# macOS
brew install azure-cli

# Ubuntu/Debian
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash

# Windows
# Download from: https://aka.ms/installazurecliwindows
```

Verify installation:
```bash
az --version
```

---

## Azure Resource Setup

### 1. Create a Resource Group

```bash
# Set variables
RESOURCE_GROUP="eoagritool-rg"
LOCATION="eastus"  # Change to your preferred region
SUBSCRIPTION_ID="your-subscription-id"

# List available subscriptions
az account list --output table

# Set the subscription
az account set --subscription $SUBSCRIPTION_ID

# Create the resource group
az group create \
  --name $RESOURCE_GROUP \
  --location $LOCATION
```

### 2. Create an App Service Plan

```bash
APP_SERVICE_PLAN="eoagritool-plan"
SKU="B2"  # Basic tier; use "S1" or "S2" for production

az appservice plan create \
  --name $APP_SERVICE_PLAN \
  --resource-group $RESOURCE_GROUP \
  --sku $SKU \
  --is-linux
```

**SKU Options:**
- `B1` / `B2` / `B3`: Basic (dev/test)
- `S1` / `S2` / `S3`: Standard (production)
- `P1V2` / `P2V2` / `P3V2`: Premium (high-performance)

### 3. Create a Web App

```bash
WEB_APP_NAME="eoagritool-prod"  # Must be globally unique

az webapp create \
  --name $WEB_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --plan $APP_SERVICE_PLAN \
  --runtime "PYTHON:3.12" \
  --deployment-container-image-name "nginx"
```

### 4. Configure Web App Settings

```bash
# Set startup command
az webapp config set \
  --name $WEB_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --startup-file "hypercorn app:app --bind 0.0.0.0:8000 --workers 2"

# Enable logging
az webapp log config \
  --name $WEB_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --docker-container-logging filesystem
```

### 5. Create Azure OpenAI Resource (if not already created)

```bash
OPENAI_ACCOUNT="eoagritool-openai"
OPENAI_SKU="S0"

az cognitiveservices account create \
  --name $OPENAI_ACCOUNT \
  --resource-group $RESOURCE_GROUP \
  --kind OpenAI \
  --sku $OPENAI_SKU \
  --location $LOCATION \
  --yes

# Get the endpoint and key
OPENAI_ENDPOINT=$(az cognitiveservices account show \
  --name $OPENAI_ACCOUNT \
  --resource-group $RESOURCE_GROUP \
  --query properties.endpoint --output tsv)

OPENAI_KEY=$(az cognitiveservices account keys list \
  --name $OPENAI_ACCOUNT \
  --resource-group $RESOURCE_GROUP \
  --query key1 --output tsv)

echo "OpenAI Endpoint: $OPENAI_ENDPOINT"
echo "OpenAI Key: $OPENAI_KEY"
```

**Deploy Azure OpenAI Model:**

```bash
# Create a deployment for a model (e.g., gpt-4 or gpt-35-turbo)
az cognitiveservices account deployment create \
  --name $OPENAI_ACCOUNT \
  --resource-group $RESOURCE_GROUP \
  --deployment-name "gpt-4-turbo" \
  --model-name "gpt-4-turbo-2024-04-09" \
  --model-version "1" \
  --sku-name "Standard" \
  --sku-capacity 10
```

### 6. Create Cosmos DB Account (Optional - for conversation history)

```bash
COSMOS_ACCOUNT="eoagritool-cosmos"

az cosmosdb create \
  --name $COSMOS_ACCOUNT \
  --resource-group $RESOURCE_GROUP \
  --kind GlobalDocumentDB \
  --default-consistency-level "Consistent Prefix"

# Get connection string
COSMOS_KEY=$(az cosmosdb keys list \
  --name $COSMOS_ACCOUNT \
  --resource-group $RESOURCE_GROUP \
  --type keys \
  --query primaryMasterKey --output tsv)

echo "Cosmos DB Key: $COSMOS_KEY"

# Create database
az cosmosdb sql database create \
  --account-name $COSMOS_ACCOUNT \
  --resource-group $RESOURCE_GROUP \
  --name "eoagritool" \
  --throughput 400

# Create container for conversations
az cosmosdb sql container create \
  --account-name $COSMOS_ACCOUNT \
  --resource-group $RESOURCE_GROUP \
  --database-name "eoagritool" \
  --name "conversations" \
  --partition-key-path "/user_id" \
  --throughput 400
```

### 7. Create Key Vault for Secrets (Recommended)

```bash
KEY_VAULT="eoagritool-kv"

az keyvault create \
  --name $KEY_VAULT \
  --resource-group $RESOURCE_GROUP

# Store secrets
az keyvault secret set \
  --vault-name $KEY_VAULT \
  --name "AzureOpenAIKey" \
  --value "$OPENAI_KEY"

az keyvault secret set \
  --vault-name $KEY_VAULT \
  --name "CosmosDbAccountKey" \
  --value "$COSMOS_KEY"

# Grant Web App access to Key Vault
PRINCIPAL_ID=$(az webapp identity assign \
  --name $WEB_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --query principalId --output tsv)

az keyvault set-policy \
  --name $KEY_VAULT \
  --object-id $PRINCIPAL_ID \
  --secret-permissions get list
```

---

## Azure DevOps Pipeline Configuration

### 1. Create an Azure DevOps Project

1. Go to [dev.azure.com](https://dev.azure.com)
2. Click **+ New project**
3. Enter project name: `EOAgriTool`
4. Select **Private** (or **Public** if open-source)
5. Click **Create**

### 2. Create a Service Connection

**In Azure DevOps:**

1. Go to **Project Settings** → **Service Connections**
2. Click **New Service Connection** → **Azure Resource Manager**
3. Select **Service Principal (Automatic)**
4. Choose your subscription and resource group
5. Name it: `Azure-EOAgriTool`
6. Click **Save**

**Note the Connection ID** for use in `azure-pipelines.yml`.

### 3. Create a Variable Group (for secrets)

1. Go to **Pipelines** → **Library**
2. Click **+ Variable group**
3. Name: `eoagritool-prod`
4. Add variables:
   - `AZURE_OPENAI_ENDPOINT` = `https://your-openai-account.openai.azure.com/`
   - `AZURE_OPENAI_MODEL` = `gpt-4-turbo`
   - `AZURE_OPENAI_PREVIEW_API_VERSION` = `2024-06-01`
   - `AZURE_COSMOSDB_ACCOUNT` = `eoagritool-cosmos`
   - `AZURE_COSMOSDB_DATABASE` = `eoagritool`
   - `AZURE_COSMOSDB_CONVERSATIONS_CONTAINER` = `conversations`

5. Add **secrets**:
   - `AzureOpenAIKey` = (paste the key from above)
   - `CosmosDbAccountKey` = (paste the key from above)

6. Click **Save**

### 4. Link GitHub Repository

1. Go to **Pipelines** → **Create Pipeline**
2. Select **GitHub**
3. Search for `aimtyaem/EOAgriTool`
4. Click **Select**
5. Choose **Existing Azure Pipelines YAML file**
6. Select branch: `gh-pages`
7. Select file: `azure-pipelines.yml`
8. Click **Save and run**

---

## Environment Variables & Secrets

### Web App Application Settings

Use Azure CLI or Azure Portal to configure:

```bash
az webapp config appsettings set \
  --name $WEB_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --settings \
    PORT=8000 \
    LOG_LEVEL=INFO \
    FLASK_DEBUG=false \
    COSMOS_INIT_TIMEOUT_SECONDS=30 \
    MAX_CONVERSATION_MESSAGES_FOR_TITLE=10 \
    MS_DEFENDER_ENABLED=false \
    APP_USER_AGENT="EOAgriTool/AsyncAzureOpenAI/2.0.0" \
    AZURE_OPENAI_PREVIEW_API_VERSION="2024-06-01" \
    AZURE_COSMOSDB_DATABASE="eoagritool" \
    AZURE_COSMOSDB_CONVERSATIONS_CONTAINER="conversations"
```

### Secret Configuration

**Option 1: Key Vault References**

```bash
# Set references to Key Vault secrets
az webapp config appsettings set \
  --name $WEB_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --settings \
    AZURE_OPENAI_KEY="@Microsoft.KeyVault(VaultName=$KEY_VAULT;SecretName=AzureOpenAIKey)" \
    AZURE_COSMOSDB_ACCOUNT_KEY="@Microsoft.KeyVault(VaultName=$KEY_VAULT;SecretName=CosmosDbAccountKey)"
```

**Option 2: Direct Configuration** (less secure)

```bash
az webapp config appsettings set \
  --name $WEB_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --settings \
    AZURE_OPENAI_KEY="$OPENAI_KEY" \
    AZURE_COSMOSDB_ACCOUNT_KEY="$COSMOS_KEY"
```

---

## Deployment Steps

### Step 1: Prepare Local Environment

```bash
# Clone the repository
git clone https://github.com/aimtyaem/EOAgriTool.git
cd EOAgriTool

# Create virtual environment
python3.12 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy and configure .env
cp .env.example .env
# Edit .env with your Azure values
```

### Step 2: Test Locally

```bash
# Set environment variables
export AZURE_OPENAI_ENDPOINT="https://your-openai-account.openai.azure.com/"
export AZURE_OPENAI_KEY="your-key"
export AZURE_OPENAI_MODEL="gpt-4-turbo"

# Run the app
python app.py

# Visit http://localhost:8000
```

### Step 3: Push to GitHub (trigger pipeline)

```bash
# Ensure you're on gh-pages branch
git checkout gh-pages

# Make changes (if any)
git add .
git commit -m "Prepare for Azure deployment"

# Push to trigger the pipeline
git push origin gh-pages
```

### Step 4: Monitor the Pipeline

1. Go to **Azure DevOps** → **Pipelines**
2. Click on the running pipeline
3. Watch **Build** and **Deploy** stages
4. Check logs for errors

### Step 5: Verify Deployment

```bash
# Check App Service status
az webapp show \
  --name $WEB_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --query state

# Stream logs
az webapp log tail \
  --name $WEB_APP_NAME \
  --resource-group $RESOURCE_GROUP
```

---

## Post-Deployment Verification

### 1. Health Check

```bash
curl https://$WEB_APP_NAME.azurewebsites.net/health

# Expected response (if all services configured):
# {"status": "healthy", "checks": {"openai": true, "cosmosdb": true}}

# Or (if only Azure OpenAI configured):
# {"status": "degraded", "checks": {"openai": true, "cosmosdb": false}}
```

### 2. Frontend Access

Visit: `https://<WEB_APP_NAME>.azurewebsites.net/`

You should see the EOAgriTool dashboard.

### 3. API Endpoints

Test the API:

```bash
# Frontend settings
curl https://$WEB_APP_NAME.azurewebsites.net/frontend_settings

# Chat endpoint (requires auth)
curl -X POST https://$WEB_APP_NAME.azurewebsites.net/conversation \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Hello"}]}'
```

### 4. Review Logs

```bash
# Application Insights (if enabled)
az monitor app-insights query \
  --app $WEB_APP_NAME \
  --resource-group $RESOURCE_GROUP

# Docker logs
az webapp log tail \
  --name $WEB_APP_NAME \
  --resource-group $RESOURCE_GROUP
```

---

## Troubleshooting

### Issue: Application fails to start

**Symptoms:**
```
ERROR - Failed to start web application
Container didn't respond to HTTP pings
```

**Solutions:**

1. Check startup command:
```bash
az webapp config show \
  --name $WEB_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --query linuxFxVersion
```

2. Verify port is 8000:
```bash
az webapp config appsettings set \
  --name $WEB_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --settings PORT=8000
```

3. Check logs:
```bash
az webapp log tail --name $WEB_APP_NAME --resource-group $RESOURCE_GROUP
```

### Issue: Azure OpenAI client initialization fails

**Error:**
```
AZURE_OPENAI_ENDPOINT or AZURE_OPENAI_RESOURCE is required
```

**Solution:**
```bash
# Verify environment variables are set
az webapp config appsettings list \
  --name $WEB_APP_NAME \
  --resource-group $RESOURCE_GROUP

# If missing, add them:
az webapp config appsettings set \
  --name $WEB_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --settings \
    AZURE_OPENAI_ENDPOINT="https://your-account.openai.azure.com/" \
    AZURE_OPENAI_MODEL="gpt-4-turbo" \
    AZURE_OPENAI_KEY="your-key"
```

### Issue: Cosmos DB connection fails

**Error:**
```
Failed to initialise CosmosDB client
```

**Solution:**

1. Verify Cosmos DB is running:
```bash
az cosmosdb show \
  --name $COSMOS_ACCOUNT \
  --resource-group $RESOURCE_GROUP
```

2. Check credentials:
```bash
az cosmosdb keys list \
  --name $COSMOS_ACCOUNT \
  --resource-group $RESOURCE_GROUP
```

3. Update the key:
```bash
az webapp config appsettings set \
  --name $WEB_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --settings \
    AZURE_COSMOSDB_ACCOUNT="$COSMOS_ACCOUNT" \
    AZURE_COSMOSDB_ACCOUNT_KEY="$COSMOS_KEY"
```

### Issue: 502 Bad Gateway

**Cause:** Application crashed or is not listening on the correct port.

**Solution:**
```bash
# Increase timeout and check logs
az webapp config set \
  --name $WEB_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --startup-file "hypercorn app:app --bind 0.0.0.0:8000 --workers 1 --timeout 120"

# Restart the app
az webapp restart \
  --name $WEB_APP_NAME \
  --resource-group $RESOURCE_GROUP

# Stream logs
az webapp log tail --name $WEB_APP_NAME --resource-group $RESOURCE_GROUP
```

### Issue: Slow performance

**Solution:**

1. Scale up the App Service Plan:
```bash
az appservice plan update \
  --name $APP_SERVICE_PLAN \
  --resource-group $RESOURCE_GROUP \
  --sku S2
```

2. Increase Hypercorn workers (in `azure-pipelines.yml`):
```yaml
startUpCommand: "hypercorn app:app --bind 0.0.0.0:$PORT --workers 4 --timeout 120"
```

3. Enable caching and enable Always On:
```bash
az webapp config set \
  --name $WEB_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --always-on true
```

---

## Cleanup (Delete Resources)

To avoid ongoing charges:

```bash
# Delete the entire resource group (all resources within it)
az group delete \
  --name $RESOURCE_GROUP \
  --yes --no-wait

# Or delete individual resources
az webapp delete --name $WEB_APP_NAME --resource-group $RESOURCE_GROUP
az appservice plan delete --name $APP_SERVICE_PLAN --resource-group $RESOURCE_GROUP
az cosmosdb delete --name $COSMOS_ACCOUNT --resource-group $RESOURCE_GROUP
az cognitiveservices account delete --name $OPENAI_ACCOUNT --resource-group $RESOURCE_GROUP
```

---

## Cost Estimation

**Monthly estimates (approximate, as of 2026):**

| Service | SKU | Cost |
|---------|-----|------|
| App Service Plan | B2 (Basic) | $15–30 |
| Azure OpenAI | S0 (Pay-per-request) | $0.03–0.15 per 1K tokens |
| Cosmos DB | 400 RU/s | $25–50 |
| Key Vault | Standard | $0.70 |
| **Total (light usage)** | — | **$40–100/month** |

For production with high traffic, expect significantly higher costs. Use Azure Cost Management to monitor spending.

---

## Additional Resources

- [Azure App Service Documentation](https://docs.microsoft.com/en-us/azure/app-service/)
- [Azure OpenAI Service Documentation](https://docs.microsoft.com/en-us/azure/cognitive-services/openai/)
- [Cosmos DB Documentation](https://docs.microsoft.com/en-us/azure/cosmos-db/)
- [Azure DevOps Pipelines](https://docs.microsoft.com/en-us/azure/devops/pipelines/)
- [Azure CLI Reference](https://docs.microsoft.com/en-us/cli/azure/)
- [Quart Documentation](https://quart.palletsprojects.com/)
- [Hypercorn Documentation](https://hypercorn.readthedocs.io/)

---

**Last Updated:** 2026-09-27  
**Version:** 1.0  
**Maintained by:** EOAgriTool Team
