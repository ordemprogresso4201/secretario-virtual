#!/bin/bash
# ============================================================================
# SETUP GCP — Configuração inicial para a Secretaria Digital IA
# ============================================================================
# Execute UMA VEZ antes do primeiro deploy:
#   bash setup_gcp.sh
# ============================================================================

set -e

echo "🔧 Configurando projeto GCP para Secretaria Digital IA..."
echo ""

PROJECT_ID=$(gcloud config get-value project 2>/dev/null)

if [ -z "$PROJECT_ID" ]; then
  echo "❌ Nenhum projeto GCP configurado."
  echo "   Execute: gcloud config set project SEU_PROJETO_ID"
  exit 1
fi

echo "📋 Projeto: $PROJECT_ID"
echo ""

# --- 1. Habilitar APIs ---
echo "🔌 Habilitando APIs necessárias..."
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  drive.googleapis.com \
  calendar-json.googleapis.com \
  --quiet

echo "✅ APIs habilitadas."
echo ""

# --- 2. Criar Artifact Registry ---
echo "📦 Criando repositório Artifact Registry..."
gcloud artifacts repositories create secretaria-digital \
  --repository-format=docker \
  --location=us-central1 \
  --description="Imagens Docker da Secretaria Digital IA" \
  --quiet 2>/dev/null || echo "   (repositório já existe — ok)"

echo "✅ Artifact Registry pronto."
echo ""

# --- 3. Permissões do Cloud Build ---
echo "🔐 Configurando permissões do Cloud Build..."

PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
CB_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${CB_SA}" \
  --role="roles/run.admin" \
  --quiet >/dev/null

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${CB_SA}" \
  --role="roles/iam.serviceAccountUser" \
  --quiet >/dev/null

echo "✅ Cloud Build com permissão de deploy no Cloud Run."
echo ""

# --- Finalização ---
echo "============================================"
echo "✅ SETUP CONCLUÍDO COM SUCESSO!"
echo "============================================"
echo ""
echo "Próximo passo — execute o deploy:"
echo ""
echo '  gcloud builds submit --config cloudbuild.yaml \'
echo '    --substitutions=\'
echo '  _GROQ_API_KEY="SUA_CHAVE",\'
echo '  _GEMINI_API_KEY="SUA_CHAVE",\'
echo '  _DRIVE_FOLDER_ID="SEU_ID",\'
echo '  _CALENDAR_ID="SEU_ID"'
echo ""
