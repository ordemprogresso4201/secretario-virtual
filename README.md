# ⚒️ Secretaria Digital IA

> **Automação Inteligente de Atas Maçônicas** — Aplicação Streamlit Serverless no Google Cloud Run

[![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python&logoColor=white)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.41-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io)
[![Cloud Run](https://img.shields.io/badge/Cloud_Run-Serverless-4285F4?logo=googlecloud&logoColor=white)](https://cloud.google.com/run)
[![License](https://img.shields.io/badge/License-Private-gray)](LICENSE)

---

## 📋 Descrição

Sistema serverless que automatiza a geração de atas maçônicas a partir de gravações de áudio estéreo. O pipeline processa o áudio em etapas sequenciais: separação de canais físicos (Venerável Mestre / Colunas), transcrição via IA de alta velocidade, formatação litúrgica com inteligência semântica e geração de documento PDF oficial — tudo integrado nativamente ao Google Workspace (Drive e Calendar).

### Pipeline de Processamento

```
📁 Upload .mp3/.wav (estéreo)
   │
   ├── 🎧 FFMPEG (subprocess)
   │      Split canal L (V.·.M.·.) e R (Colunas)
   │
   ├── 🎙️ Groq Whisper-large-v3
   │      Transcrição paralela (ThreadPoolExecutor)
   │      Merge cronológico com timestamps
   │
   ├── 🤖 Gemini 1.5 Flash
   │      Prompt litúrgico com siglas maçônicas
   │      Proteção PII automática
   │
   ├── 📄 ReportLab
   │      PDF justificado A4 + blocos de assinatura
   │
   └── ☁️ Google Workspace (ADC)
          Drive: Upload + link público
          Calendar: Patch evento + notificação
```

---

## 🏗️ Arquitetura

A aplicação segue uma arquitetura **stateless** otimizada para os limites de memória de contêineres serverless:

- **Armazenamento efêmero:** Todos os arquivos são salvos exclusivamente em `/tmp/`
- **Garbage Collection:** Blocos `try/finally` com `os.remove()` iterativo em toda requisição
- **Autenticação ADC:** Herda a identidade do Cloud Run via `google.auth.default()` — sem `credentials.json`
- **Sem pydub:** FFMPEG chamado via `subprocess.run()` para evitar carregamento de áudio bruto na RAM

---

## 📂 Estrutura do Projeto

```
secretaria-digital-ia/
├── app.py                    # Interface Streamlit + orquestração do pipeline
├── core/
│   ├── __init__.py            # Pacote core
│   ├── audio_engine.py        # FFMPEG subprocess + Groq STT multi-thread
│   ├── llm_agent.py           # Gemini 1.5 Flash + prompt litúrgico maçônico
│   ├── pdf_builder.py         # ReportLab: PDF justificado A4 + assinaturas
│   └── gcp_services.py        # Google Drive + Calendar via ADC nativo
├── requirements.txt           # Dependências pinadas
├── Dockerfile                 # python:3.11-slim + ffmpeg + porta 8080
├── .dockerignore              # Exclusões de build
└── README.md                  # Esta documentação
```

---

## 🔧 Pré-requisitos

| Requisito | Versão | Descrição |
|---|---|---|
| Python | 3.11+ | Linguagem principal |
| Docker | 20+ | Build e execução local |
| GCP Account | — | Cloud Run + APIs (Drive, Calendar) |
| Groq API Key | — | Transcrição STT com Whisper |
| Gemini API Key | — | Formatação de ata com LLM |

### APIs GCP Necessárias

```bash
gcloud services enable run.googleapis.com
gcloud services enable drive.googleapis.com
gcloud services enable calendar-json.googleapis.com
```

---

## ⚙️ Variáveis de Ambiente

| Variável | Obrigatória | Descrição |
|---|---|---|
| `GROQ_API_KEY` | ✅ Sim | Chave da API Groq para Whisper STT (whisper-large-v3) |
| `GEMINI_API_KEY` | ✅ Sim | Chave da API Google AI Studio (Gemini 1.5 Flash) |
| `DRIVE_FOLDER_ID` | ❌ Opcional | ID da pasta no Google Drive para upload do PDF |
| `CALENDAR_ID` | ❌ Opcional | ID do calendário Google para atualização de eventos |

> **Nota:** Se variáveis obrigatórias estiverem ausentes, a aplicação exibirá uma mensagem de erro amigável na interface.

---

## 🚀 Instalação e Uso

### Execução Local (Docker)

```bash
# 1. Clone o repositório
git clone https://github.com/flpmrn/itcia-sync-api.git
cd itcia-sync-api

# 2. Build da imagem
docker build -t secretaria-digital-ia .

# 3. Execute com variáveis de ambiente
docker run -p 8080:8080 \
  -e GROQ_API_KEY="sua_chave_groq" \
  -e GEMINI_API_KEY="sua_chave_gemini" \
  -e DRIVE_FOLDER_ID="id_da_pasta_drive" \
  -e CALENDAR_ID="id_do_calendario" \
  secretaria-digital-ia
```

Acesse: **http://localhost:8080**

### Execução Local (sem Docker)

```bash
# 1. Instale o ffmpeg no sistema
# Ubuntu/Debian:
sudo apt-get install -y ffmpeg
# macOS:
brew install ffmpeg

# 2. Instale dependências Python
pip install -r requirements.txt

# 3. Configure variáveis de ambiente
export GROQ_API_KEY="sua_chave_groq"
export GEMINI_API_KEY="sua_chave_gemini"

# 4. Execute
streamlit run app.py --server.port=8080
```

---

## ☁️ Deploy no Google Cloud Run

```bash
# 1. Tag da imagem para Google Container Registry
docker tag secretaria-digital-ia gcr.io/SEU_PROJETO_GCP/secretaria-digital-ia:latest

# 2. Push para o GCR
docker push gcr.io/SEU_PROJETO_GCP/secretaria-digital-ia:latest

# 3. Deploy no Cloud Run
gcloud run deploy secretaria-digital-ia \
  --image gcr.io/SEU_PROJETO_GCP/secretaria-digital-ia:latest \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 1Gi \
  --timeout 600 \
  --set-env-vars "GROQ_API_KEY=xxx,GEMINI_API_KEY=xxx,DRIVE_FOLDER_ID=xxx,CALENDAR_ID=xxx"
```

### Configuração da Service Account

A Service Account do Cloud Run precisa das seguintes permissões:

- `roles/iam.serviceAccountUser`
- Google Drive API (escopo `drive`)
- Google Calendar API (escopo `calendar`)

---

## 📦 Dependências

| Pacote | Versão | Função |
|---|---|---|
| `streamlit` | 1.41.1 | Interface web interativa |
| `groq` | 0.15.0 | SDK da API Groq (Whisper STT) |
| `google-genai` | 1.5.0 | SDK do Gemini (Google AI Studio) |
| `reportlab` | 4.2.5 | Geração de PDF programática |
| `google-api-python-client` | 2.159.0 | APIs Google (Drive, Calendar) |
| `google-auth` | 2.37.0 | Autenticação ADC nativa |

### Dependência de Sistema

- **ffmpeg** — Instalado no Dockerfile via `apt-get`. Necessário para separação de canais estéreo.

---

## 🧩 Módulos

### `core/audio_engine.py`

Engine de áudio que processa gravações estéreo:

- **`split_stereo_channels(input_path)`** — Chama `ffmpeg` via `subprocess.run()` para separar canal L (Venerável Mestre) e R (Colunas) em arquivos mono independentes
- **`transcribe_channels(left_path, right_path, groq_api_key)`** — Envia ambos os canais em paralelo via `ThreadPoolExecutor` para a API Groq (modelo `whisper-large-v3`), obtem segmentos com timestamps
- **`format_merged_transcript(segments)`** — Mescla cronologicamente os segmentos de ambos os canais em texto formatado para o LLM

### `core/llm_agent.py`

Agente de inteligência semântica litúrgica:

- **`format_ata(raw_transcript, template_type, gemini_api_key)`** — Envia transcrição ao Gemini 1.5 Flash com System Prompt especializado
- **System Prompt** inclui: redação em 3ª pessoa, siglas maçônicas (A.·.R.·.L.·.S.·., V.·.M.·., G.·.A.·.D.·.U.·.), estrutura oficial de ata (9 seções), proteção PII automática
- **6 templates** de sessão disponíveis (Graus 1, 2, 3 + Sessão Magna)

### `core/pdf_builder.py`

Gerador de documentos PDF:

- **`generate_pdf(ata_text, template_type, output_path)`** — Produz PDF A4 justificado com ReportLab
- Layout profissional: margens de 2.5cm, fonte Helvetica 11pt, recuo de primeira linha
- Detecção automática de seções (headers markdown/bold)
- Blocos de assinatura no rodapé: V.·.M.·., Orador, Secretário
- Numeração de páginas automática

### `core/gcp_services.py`

Integração nativa com Google Workspace:

- **`upload_to_drive(pdf_path, filename, folder_id)`** — Upload via Drive API v3 com permissão pública de leitura (`anyone/reader`), retorna `webViewLink`
- **`patch_calendar_event(calendar_id, web_view_link)`** — Busca evento do dia atual (00:00–23:59 UTC), aplica patch na descrição com link da ata, dispara `sendUpdates='all'` para notificar convidados
- Autenticação via `google.auth.default()` (ADC — Application Default Credentials)

---

## 🔒 Segurança

- **Segredos:** Todas as API keys via `os.environ.get()` — nunca hardcoded
- **ADC Nativo:** Sem arquivos `credentials.json` — herda identidade do Cloud Run
- **Proteção PII:** O prompt do Gemini mascara automaticamente dados sensíveis (bancários, médicos, endereços)
- **Validação de Input:** Verificação de existência de arquivos e conteúdo antes do processamento
- **Exceções Específicas:** Tratamento granular (`FileNotFoundError`, `RuntimeError`, `ValueError`)
- **Logging Estruturado:** Módulo `logging` em todos os módulos — sem `print()`

---

## 📄 Licença

Projeto privado. Todos os direitos reservados.
