# ✦ Lúmen.IA — Secretaria Digital Autônoma

> **Automação Inteligente de Atas Maçônicas** — Streamlit + Dark Glassmorphism no Google Cloud Run

[![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python&logoColor=white)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.41-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io)
[![Cloud Run](https://img.shields.io/badge/Cloud_Run-Serverless-4285F4?logo=googlecloud&logoColor=white)](https://cloud.google.com/run)
[![Gemini](https://img.shields.io/badge/Gemini_2.0-Flash-8E75B2?logo=googlegemini&logoColor=white)](https://ai.google.dev)
[![License](https://img.shields.io/badge/License-Private-gray)](LICENSE)

---

## 📋 Descrição

Sistema serverless que automatiza a geração de atas maçônicas a partir de gravações de áudio estéreo (ou mono). O pipeline processa o áudio em etapas sequenciais: detecção automática de canais, separação física (Venerável Mestre / Colunas), transcrição via IA de alta velocidade, formatação litúrgica com inteligência semântica e geração de documento PDF oficial — tudo integrado nativamente ao Google Workspace (Drive e Calendar).

### Pipeline de Processamento

```
📁 Upload .mp3/.wav/.m4a/.ogg (estéreo ou mono)
   │
   ├── 🎧 Demosaico Acústico FFMPEG
   │      Detecção automática mono/estéreo (ffprobe)
   │      Split canal L (V.·.M.·.) e R (Colunas)
   │      Mono: duplicação automática para ambos canais
   │
   ├── 🎙️ Transcrição Turbo Groq
   │      Motor Whisper-large-v3 em paralelo (ThreadPoolExecutor)
   │      Merge cronológico com timestamps
   │
   ├── 🤖 Linting Litúrgico Gemini 2.0 Flash
   │      Prompt litúrgico com siglas maçônicas (∴)
   │      Proteção PII automática
   │      Retry automático com backoff (429/rate-limit)
   │
   ├── 📄 ReportLab
   │      PDF justificado A4 + blocos de assinatura
   │
   └── ☁️ Sincronização GCP Workspace
          Drive: Upload + link público
          Calendar: Patch evento + notificação
```

---

## 🏗️ Arquitetura

A aplicação segue uma arquitetura **stateless** otimizada para contêineres serverless:

- **Armazenamento efêmero:** Todos os arquivos salvos exclusivamente em `/tmp/`
- **Garbage Collection:** Blocos `try/finally` com `os.remove()` iterativo em toda requisição
- **Autenticação ADC:** Herda a identidade do Cloud Run via `google.auth.default()` — sem `credentials.json`
- **Sem pydub:** FFMPEG chamado via `subprocess.run()` para evitar carregamento bruto na RAM
- **Detecção inteligente:** `ffprobe` identifica canais (mono/estéreo) antes do processamento
- **Tolerância a falhas:** Retry com backoff exponencial (15s, 30s, 60s) para erros 429 do Gemini

### Recursos do Cloud Run

| Recurso | Valor |
|---|---|
| **Memória** | 2 GiB |
| **CPU** | 2 vCPUs |
| **Timeout** | 600 segundos |
| **Concorrência** | 1 (processamento de áudio intensivo) |
| **Máx. instâncias** | 3 |
| **Escalonamento mín.** | 0 (scale to zero) |

---

## 📂 Estrutura do Projeto

```
secretaria-digital-ia/
├── app.py                     # Interface Lúmen.IA (Dark Glassmorphism) + pipeline
├── core/
│   ├── __init__.py            # Pacote core
│   ├── audio_engine.py        # FFMPEG + ffprobe (mono/estéreo) + Groq STT
│   ├── llm_agent.py           # Gemini 2.0 Flash + retry 429 + prompt litúrgico
│   ├── pdf_builder.py         # ReportLab: PDF justificado A4 + assinaturas
│   └── gcp_services.py        # Google Drive + Calendar via ADC nativo
├── .streamlit/
│   └── config.toml            # Tema dark (indigo/void)
├── cloudbuild.yaml            # Pipeline CI/CD (build + push + deploy)
├── setup_gcp.sh               # Script de setup inicial do GCP
├── requirements.txt           # Dependências pinadas
├── Dockerfile                 # python:3.11-slim + ffmpeg + CORS/XSRF desabilitado
├── .dockerignore              # Exclusões de build
├── DEPLOY_CLOUD_RUN.md        # Guia de deploy simplificado
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
| Gemini API Key | — | Formatação de ata com LLM (Gemini 2.0 Flash) |

### APIs GCP Necessárias

```bash
gcloud services enable run.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable artifactregistry.googleapis.com
gcloud services enable drive.googleapis.com
gcloud services enable calendar-json.googleapis.com
```

---

## ⚙️ Variáveis de Ambiente

| Variável | Obrigatória | Descrição |
|---|---|---|
| `GROQ_API_KEY` | ✅ Sim | Chave da API Groq para Whisper STT (whisper-large-v3) |
| `GEMINI_API_KEY` | ✅ Sim | Chave da API Google AI Studio (Gemini 2.0 Flash) |
| `DRIVE_FOLDER_ID` | ❌ Opcional | ID da pasta no Google Drive para upload do PDF |
| `CALENDAR_ID` | ❌ Opcional | Email do calendário Google (ex: `user@gmail.com`) |

> **Nota:** Se variáveis obrigatórias estiverem ausentes, a aplicação exibirá uma mensagem de erro amigável na interface.

---

## 🚀 Deploy (Cloud Build — Recomendado)

O método mais simples para deploy usa o `cloudbuild.yaml` integrado:

```bash
# 1. Clone o repositório
git clone https://github.com/ordemprogresso4201/secretario-virtual.git
cd secretario-virtual

# 2. Execute o setup inicial (uma vez)
chmod +x setup_gcp.sh && ./setup_gcp.sh

# 3. Deploy via Cloud Build
gcloud builds submit \
  --config cloudbuild.yaml \
  --substitutions=\
_GROQ_API_KEY="sua_chave_groq",\
_GEMINI_API_KEY="sua_chave_gemini",\
_DRIVE_FOLDER_ID="id_da_pasta_drive",\
_CALENDAR_ID="seu_email@gmail.com"
```

O pipeline automatiza: **Build Docker → Push para Artifact Registry → Deploy no Cloud Run**.

### Execução Local (Docker)

```bash
# Build
docker build -t lumen-ia .

# Run
docker run -p 8080:8080 \
  -e GROQ_API_KEY="sua_chave_groq" \
  -e GEMINI_API_KEY="sua_chave_gemini" \
  -e DRIVE_FOLDER_ID="id_da_pasta_drive" \
  -e CALENDAR_ID="seu_email@gmail.com" \
  lumen-ia
```

Acesse: **http://localhost:8080**

---

## 📦 Dependências

| Pacote | Versão | Função |
|---|---|---|
| `streamlit` | 1.41.1 | Interface web interativa |
| `groq` | 0.15.0 | SDK da API Groq (Whisper STT) |
| `google-genai` | 1.5.0 | SDK do Gemini 2.0 Flash (Google AI Studio) |
| `reportlab` | 4.2.5 | Geração de PDF programática |
| `google-api-python-client` | 2.159.0 | APIs Google (Drive, Calendar) |
| `google-auth` | 2.37.0 | Autenticação ADC nativa |

### Dependência de Sistema

- **ffmpeg** — Instalado no Dockerfile via `apt-get`. Necessário para separação de canais e detecção via ffprobe.

---

## 🧩 Módulos

### `core/audio_engine.py`

Engine de áudio com detecção automática de canais:

- **`_get_audio_channels(input_path)`** — Usa `ffprobe` para detectar se o áudio é mono (1 canal) ou estéreo (2+ canais)
- **`split_stereo_channels(input_path)`** — Estéreo: separa L (V.·.M.·.) e R (Colunas). Mono: duplica para ambos os caminhos
- **`transcribe_channels(left_path, right_path, groq_api_key)`** — Transcrição paralela via `ThreadPoolExecutor` com Groq Whisper-large-v3
- **`format_merged_transcript(segments)`** — Merge cronológico com timestamps e identificação de falante

### `core/llm_agent.py`

Agente de inteligência semântica litúrgica com tolerância a falhas:

- **`format_ata(raw_transcript, template_type, gemini_api_key)`** — Gemini 2.0 Flash com System Prompt especializado
- **Retry automático:** 3 tentativas com backoff exponencial (15s, 30s, 60s) para erros 429
- **System Prompt** inclui: redação em 3ª pessoa, siglas maçônicas (A.·.R.·.L.·.S.·., V.·.M.·., G.·.A.·.D.·.U.·.), estrutura oficial de ata (9 seções), proteção PII automática
- **6 templates** de sessão disponíveis (Graus 1, 2, 3 + Sessão Magna)

### `core/pdf_builder.py`

Gerador de documentos PDF:

- **`generate_pdf(ata_text, template_type, output_path)`** — PDF A4 justificado com ReportLab
- Layout profissional: margens 2.5cm, Helvetica 11pt, recuo de primeira linha
- Detecção automática de seções (headers markdown/bold)
- Blocos de assinatura: V.·.M.·., Orador, Secretário
- Numeração de páginas automática

### `core/gcp_services.py`

Integração nativa com Google Workspace:

- **`upload_to_drive(pdf_path, filename, folder_id)`** — Upload via Drive API v3 com permissão pública, retorna `webViewLink`
- **`patch_calendar_event(calendar_id, web_view_link)`** — Busca evento do dia, patch na descrição com link da ata, `sendUpdates='all'`
- Autenticação via `google.auth.default()` (ADC nativo — sem credentials.json)

---

## 🎨 Interface

A interface usa um design **Dark Glassmorphism** com:

- Background `#050507` (void) com aurora glow orbs animados
- Cards com `backdrop-filter: blur(40px)` e bordas semi-transparentes
- Layout two-column: Workspace (7/12) + Log de Operações (5/12)
- Timeline em tempo real com estados: idle → processing → complete
- Botão gradient indigo com glow effect
- Badge "GCP Online" com pulse animation
- Tema Streamlit customizado via `.streamlit/config.toml`

---

## 🔒 Segurança

- **Segredos:** Todas as API keys via `os.environ.get()` — nunca hardcoded
- **ADC Nativo:** Sem arquivos `credentials.json` — herda identidade do Cloud Run
- **Proteção PII:** O prompt do Gemini mascara automaticamente dados sensíveis
- **CORS/XSRF:** Desabilitados no Dockerfile para compatibilidade com proxy Cloud Run
- **Validação de Input:** Verificação de existência de arquivos e conteúdo
- **Exceções Específicas:** Tratamento granular com retry para erros transientes
- **Logging Estruturado:** Módulo `logging` em todos os módulos — sem `print()`

---

## 📄 Licença

Projeto privado. Todos os direitos reservados.
