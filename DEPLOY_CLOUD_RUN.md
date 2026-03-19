# 🚀 DEPLOY — Secretaria Digital IA no Google Cloud Run

> Guia simplificado: **3 comandos** para colocar a aplicação no ar.

---

## ⚡ DEPLOY RÁPIDO (para quem quer ir direto)

Já tem tudo configurado? Execute estes 3 comandos:

```bash
# 1. Clone o repositório
git clone https://github.com/flpmrn/secretario-virtual.git
cd secretario-virtual

# 2. Configuração inicial (executar APENAS na primeira vez)
bash setup_gcp.sh

# 3. Deploy automático (build + push + deploy em um único comando)
gcloud builds submit --config cloudbuild.yaml \
  --substitutions=\
_GROQ_API_KEY="COLE_SUA_CHAVE_GROQ_AQUI",\
_GEMINI_API_KEY="COLE_SUA_CHAVE_GEMINI_AQUI",\
_DRIVE_FOLDER_ID="COLE_O_ID_DA_PASTA_DRIVE",\
_CALENDAR_ID="COLE_O_ID_DO_CALENDARIO"
```

**Pronto!** O Cloud Build vai construir, enviar e publicar automaticamente. A URL final aparecerá no terminal.

---

## 📝 GUIA PASSO A PASSO (para quem nunca usou GCP)

### Passo 1 — Criar conta e projeto no Google Cloud

1. Acesse **https://console.cloud.google.com**
2. Crie uma conta Google Cloud (tem **$300 de crédito grátis** por 90 dias)
3. Clique em **"Selecionar Projeto"** → **"Novo Projeto"**
4. Nomeie como `secretaria-digital` e clique **Criar**
5. Aguarde a criação e selecione o projeto criado

### Passo 2 — Abrir o Cloud Shell

1. No canto superior direito do Console GCP, clique no ícone **`>_`** (Cloud Shell)
2. Um terminal vai abrir na parte inferior da tela — é por aqui que faremos tudo

### Passo 3 — Clonar o código

```bash
git clone https://github.com/flpmrn/secretario-virtual.git
cd secretario-virtual
```

### Passo 4 — Configuração inicial (UMA VEZ)

```bash
# Habilita as APIs necessárias
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  drive.googleapis.com \
  calendar-json.googleapis.com

# Cria o repositório de imagens Docker
gcloud artifacts repositories create secretaria-digital \
  --repository-format=docker \
  --location=us-central1 \
  --description="Imagens Docker da Secretaria Digital IA" \
  --quiet

# Concede permissão ao Cloud Build para fazer deploy
PROJECT_NUMBER=$(gcloud projects describe $(gcloud config get-value project) --format='value(projectNumber)')

gcloud projects add-iam-policy-binding $(gcloud config get-value project) \
  --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
  --role="roles/run.admin" \
  --quiet

gcloud projects add-iam-policy-binding $(gcloud config get-value project) \
  --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser" \
  --quiet

echo "✅ Configuração inicial concluída!"
```

### Passo 5 — Obter as chaves de API

| Chave | Onde obter | O que é |
|---|---|---|
| `GROQ_API_KEY` | [console.groq.com/keys](https://console.groq.com/keys) | Transcrição de áudio |
| `GEMINI_API_KEY` | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) | Formatação da ata por IA |
| `DRIVE_FOLDER_ID` | URL da pasta do Drive* | Onde salvar os PDFs |
| `CALENDAR_ID` | Config. do Google Calendar** | Para notificar os IIr.·. |

> \* **Como pegar o DRIVE_FOLDER_ID:** Abra a pasta no Google Drive. A URL será algo como `https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOp`. O ID é `1AbCdEfGhIjKlMnOp`.

> \*\* **Como pegar o CALENDAR_ID:** No Google Calendar, clique em ⚙️ → Configurações da agenda → Role até "Integrar agenda". O ID geralmente é um email como `xyzabc@group.calendar.google.com`.

### Passo 6 — Deploy!

```bash
gcloud builds submit --config cloudbuild.yaml \
  --substitutions=\
_GROQ_API_KEY="COLE_AQUI",\
_GEMINI_API_KEY="COLE_AQUI",\
_DRIVE_FOLDER_ID="COLE_AQUI",\
_CALENDAR_ID="COLE_AQUI"
```

Aguarde ~5 minutos. Quando finalizar, copie a URL que aparecerá no terminal.

### Passo 7 — Compartilhar acesso ao Drive e Calendar

**IMPORTANTE:** Para que a aplicação consiga enviar PDFs e atualizar o calendário:

1. **Google Drive:** Abra a pasta → Clique em **Compartilhar** → Adicione o email da Service Account do Cloud Run (encontre em: Console GCP → Cloud Run → Selecione o serviço → aba "Segurança" → Service Account)
2. **Google Calendar:** Configurações → Compartilhar com pessoas → Adicione o mesmo email da Service Account com permissão **"Fazer alterações em eventos"**

---

## 🔄 ATUALIZAR A APLICAÇÃO

Quando houver atualizações no código, basta executar novamente:

```bash
cd secretario-virtual
git pull
gcloud builds submit --config cloudbuild.yaml \
  --substitutions=\
_GROQ_API_KEY="SUA_CHAVE",\
_GEMINI_API_KEY="SUA_CHAVE",\
_DRIVE_FOLDER_ID="SEU_ID",\
_CALENDAR_ID="SEU_ID"
```

---

## ❓ PROBLEMAS COMUNS

| Problema | Solução |
|---|---|
| "APIs not enabled" | Execute novamente o `gcloud services enable ...` do Passo 4 |
| "Permission denied" | Execute novamente os comandos `add-iam-policy-binding` do Passo 4 |
| "Repository not found" | Execute o `gcloud artifacts repositories create ...` do Passo 4 |
| Build demora mais de 10 min | Normal na primeira vez (download das dependências Python) |
| App não envia PDF ao Drive | Compartilhe a pasta do Drive com a Service Account (Passo 7) |
| App não atualiza o Calendar | Compartilhe o calendário com a Service Account (Passo 7) |
| Tela mostra erro de env vars | Verifique se colou as chaves corretamente no `--substitutions` |
| "Memory limit exceeded" | Edite `cloudbuild.yaml` → mude `_MEMORY: 1Gi` para `_MEMORY: 2Gi` |

---

## 💰 QUANTO CUSTA?

| Item | Custo |
|---|---|
| Cloud Run (quando ninguém usa) | **$0** (escala a zero) |
| Cloud Run (processando uma ata) | ~$0.01 por execução |
| Artifact Registry | ~$0.10/mês |
| Drive e Calendar APIs | Gratuito |
| **Total mensal estimado** | **$1–5/mês** (uso moderado) |
