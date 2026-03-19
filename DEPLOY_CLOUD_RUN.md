# PROMPT DE DEPLOY — Secretaria Digital IA no Google Cloud Run

> **Contexto:** Você é um agente de infraestrutura GCP. Sua tarefa é configurar e deployar a aplicação "Secretaria Digital IA" (Streamlit) no Google Cloud Run. Siga TODOS os passos abaixo na ordem exata. NÃO pule nenhuma etapa.

---

## 1. PRÉ-REQUISITOS

Confirme que os seguintes itens estão disponíveis antes de prosseguir:

- [ ] **Google Cloud CLI (`gcloud`)** instalado e autenticado
- [ ] **Docker** instalado e funcional
- [ ] **Repositório clonado:** `git clone https://github.com/flpmrn/secretario-virtual.git`
- [ ] **API Keys obtidas:**
  - `GROQ_API_KEY` — obtida em https://console.groq.com/keys
  - `GEMINI_API_KEY` — obtida em https://aistudio.google.com/apikey
- [ ] **IDs do Google Workspace:**
  - `DRIVE_FOLDER_ID` — ID da pasta de destino no Google Drive (extrair da URL da pasta)
  - `CALENDAR_ID` — ID do calendário do Google (geralmente o email do calendário compartilhado)

---

## 2. CONFIGURAÇÃO DO PROJETO GCP

```bash
# Defina o ID do seu projeto GCP (substitua pelo seu)
export GCP_PROJECT_ID="seu-projeto-gcp"

# Autentique e configure o projeto
gcloud auth login
gcloud config set project $GCP_PROJECT_ID

# Habilite as APIs necessárias (TODAS obrigatórias)
gcloud services enable run.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable artifactregistry.googleapis.com
gcloud services enable drive.googleapis.com
gcloud services enable calendar-json.googleapis.com
```

---

## 3. CRIAÇÃO DO ARTIFACT REGISTRY (recomendado sobre GCR)

```bash
# Crie um repositório Docker no Artifact Registry
gcloud artifacts repositories create secretaria-digital \
  --repository-format=docker \
  --location=us-central1 \
  --description="Imagens Docker da Secretaria Digital IA"

# Configure o Docker para autenticar no Artifact Registry
gcloud auth configure-docker us-central1-docker.pkg.dev
```

---

## 4. BUILD E PUSH DA IMAGEM DOCKER

```bash
# Navegue até o diretório do projeto
cd secretario-virtual

# Build da imagem Docker
docker build -t secretaria-digital-ia .

# Tag para o Artifact Registry
docker tag secretaria-digital-ia \
  us-central1-docker.pkg.dev/$GCP_PROJECT_ID/secretaria-digital/secretaria-digital-ia:latest

# Push da imagem
docker push \
  us-central1-docker.pkg.dev/$GCP_PROJECT_ID/secretaria-digital/secretaria-digital-ia:latest
```

### ALTERNATIVA: Build via Cloud Build (sem Docker local)

```bash
gcloud builds submit --tag \
  us-central1-docker.pkg.dev/$GCP_PROJECT_ID/secretaria-digital/secretaria-digital-ia:latest
```

---

## 5. CONFIGURAÇÃO DA SERVICE ACCOUNT

```bash
# Crie uma Service Account dedicada
gcloud iam service-accounts create secretaria-digital-sa \
  --display-name="Secretaria Digital IA Service Account"

# Atribua permissões para Drive e Calendar
# (Alternativa: usar Domain-Wide Delegation se for Google Workspace)

# Conceda permissão de invoker ao Cloud Run
gcloud projects add-iam-policy-binding $GCP_PROJECT_ID \
  --member="serviceAccount:secretaria-digital-sa@$GCP_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.invoker"
```

### IMPORTANTE — Permissões no Google Drive e Calendar:

A Service Account precisa de acesso direto:

1. **Google Drive:** Compartilhe a pasta de destino com o email da Service Account (`secretaria-digital-sa@SEU_PROJETO.iam.gserviceaccount.com`) com permissão de **Editor**
2. **Google Calendar:** Adicione o email da Service Account como convidado do calendário com permissão de **Fazer alterações em eventos**

---

## 6. DEPLOY NO CLOUD RUN

```bash
# Substitua os valores XXX pelas suas chaves reais
gcloud run deploy secretaria-digital-ia \
  --image us-central1-docker.pkg.dev/$GCP_PROJECT_ID/secretaria-digital/secretaria-digital-ia:latest \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 2 \
  --timeout 600 \
  --max-instances 3 \
  --min-instances 0 \
  --concurrency 1 \
  --service-account secretaria-digital-sa@$GCP_PROJECT_ID.iam.gserviceaccount.com \
  --set-env-vars "\
GROQ_API_KEY=SUBSTITUA_PELA_CHAVE_GROQ,\
GEMINI_API_KEY=SUBSTITUA_PELA_CHAVE_GEMINI,\
DRIVE_FOLDER_ID=SUBSTITUA_PELO_ID_DA_PASTA,\
CALENDAR_ID=SUBSTITUA_PELO_ID_DO_CALENDARIO"
```

### Parâmetros Críticos Explicados:

| Parâmetro | Valor | Motivo |
|---|---|---|
| `--memory 1Gi` | 1 GB RAM | Suficiente para processamento de áudio via ffmpeg |
| `--cpu 2` | 2 vCPUs | Paralelismo na transcrição Groq (ThreadPoolExecutor) |
| `--timeout 600` | 10 minutos | Áudios longos exigem tempo de processamento |
| `--max-instances 3` | Máx. 3 | Limita custo; cada sessão é independente |
| `--min-instances 0` | Escala a zero | Serverless — sem custo quando ocioso |
| `--concurrency 1` | 1 req/instância | Streamlit é single-threaded por natureza |

---

## 7. VERIFICAÇÃO PÓS-DEPLOY

```bash
# 1. Obtenha a URL do serviço
gcloud run services describe secretaria-digital-ia \
  --region us-central1 \
  --format="value(status.url)"

# 2. Teste o health check
curl -s $(gcloud run services describe secretaria-digital-ia \
  --region us-central1 \
  --format="value(status.url)")/_stcore/health

# 3. Verifique os logs
gcloud run services logs read secretaria-digital-ia \
  --region us-central1 \
  --limit 50
```

### Checklist de Validação:

- [ ] URL do Cloud Run retorna a interface Streamlit
- [ ] Página carrega sem erro de variáveis de ambiente
- [ ] ffmpeg está disponível no contêiner (verificar nos logs durante processamento)
- [ ] Upload de áudio de teste funciona
- [ ] PDF é gerado e oferecido para download
- [ ] Upload ao Drive funciona (arquivo aparece na pasta)
- [ ] Calendar é atualizado com o link da ata

---

## 8. ATUALIZAÇÕES FUTURAS

Para deployar novas versões após alterações no código:

```bash
# Rebuild
docker build -t secretaria-digital-ia .

# Tag nova versão
docker tag secretaria-digital-ia \
  us-central1-docker.pkg.dev/$GCP_PROJECT_ID/secretaria-digital/secretaria-digital-ia:latest

# Push
docker push \
  us-central1-docker.pkg.dev/$GCP_PROJECT_ID/secretaria-digital/secretaria-digital-ia:latest

# Redeploy (usa mesma imagem tag :latest)
gcloud run services update secretaria-digital-ia \
  --region us-central1 \
  --image us-central1-docker.pkg.dev/$GCP_PROJECT_ID/secretaria-digital/secretaria-digital-ia:latest
```

---

## 9. TROUBLESHOOTING

| Problema | Causa Provável | Solução |
|---|---|---|
| `FFMPEG not found` | ffmpeg não instalado na imagem | Verificar `RUN apt-get install -y ffmpeg` no Dockerfile |
| `DefaultCredentialsError` | Service Account sem permissão | Compartilhar pasta Drive e Calendar com o email da SA |
| `Memory limit exceeded` | Áudio muito grande na RAM | Aumentar `--memory` para `2Gi` |
| `Timeout` | Processamento longo | Aumentar `--timeout` para `900` |
| `GROQ_API_KEY not set` | Env var ausente | Verificar `--set-env-vars` no deploy |
| `Permission denied (Drive)` | SA sem acesso à pasta | Compartilhar pasta com email da SA como Editor |
| `No events found (Calendar)` | SA sem acesso ao calendário | Adicionar SA como convidado do calendário |
| Porta errada | Conflito de porta | Confirmar `ENV PORT=8080` no Dockerfile e `--server.port=8080` no CMD |

---

## 10. ESTIMATIVA DE CUSTOS (Cloud Run)

| Recurso | Estimativa Mensal (uso moderado) |
|---|---|
| Cloud Run (CPU/RAM) | ~$5–15 (scale-to-zero) |
| Artifact Registry | ~$0.10/GB armazenado |
| Cloud Build (se usado) | ~$0.003/minuto de build |
| Google Drive API | Gratuito (cota padrão) |
| Google Calendar API | Gratuito (cota padrão) |
| **Total estimado** | **~$5–20/mês** |

> **Nota:** Com `--min-instances 0`, o custo é praticamente zero quando a aplicação não está em uso. Cobranças ocorrem apenas durante o processamento ativo de atas.
