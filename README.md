# ⚒️ Secretaria Digital IA

Automação Inteligente de Atas Maçônicas · Serverless no Google Cloud Run

## Arquitetura

```
Upload .mp3 (estéreo)
    │
    ├── FFMPEG (subprocess) → split L/R
    │       │
    │       ├── Groq Whisper (L) ─┐
    │       └── Groq Whisper (R) ─┤ ThreadPoolExecutor
    │                             │
    │                    Merge cronológico
    │                             │
    ├── Gemini 1.5 Flash (prompt litúrgico) → Ata formatada
    │                             │
    ├── ReportLab → PDF justificado + assinaturas
    │                             │
    ├── Google Drive (ADC) → Upload + link público
    └── Google Calendar (ADC) → Patch evento + notificação
```

## Estrutura do Projeto

```
.
├── app.py                 # Interface Streamlit + orquestração
├── core/
│   ├── __init__.py
│   ├── audio_engine.py    # FFMPEG + Groq STT paralelo
│   ├── llm_agent.py       # Gemini + prompt litúrgico
│   ├── pdf_builder.py     # ReportLab PDF
│   └── gcp_services.py    # Drive + Calendar (ADC)
├── requirements.txt
├── Dockerfile
└── .dockerignore
```

## Pré-requisitos

- Docker instalado localmente
- Conta GCP com Cloud Run habilitado
- APIs habilitadas: Drive API, Calendar API
- Chaves: `GROQ_API_KEY`, `GEMINI_API_KEY`

## Variáveis de Ambiente

| Variável | Obrigatória | Descrição |
|---|---|---|
| `GROQ_API_KEY` | ✅ | API key do Groq para Whisper STT |
| `GEMINI_API_KEY` | ✅ | API key do Google AI Studio (Gemini) |
| `DRIVE_FOLDER_ID` | ❌ | ID da pasta do Drive para upload |
| `CALENDAR_ID` | ❌ | ID do calendário para atualização |

## Deploy no Cloud Run

```bash
# Build da imagem
docker build -t secretaria-digital-ia .

# Tag para o GCR
docker tag secretaria-digital-ia gcr.io/SEU_PROJETO/secretaria-digital-ia

# Push
docker push gcr.io/SEU_PROJETO/secretaria-digital-ia

# Deploy
gcloud run deploy secretaria-digital-ia \
  --image gcr.io/SEU_PROJETO/secretaria-digital-ia \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 1Gi \
  --timeout 600 \
  --set-env-vars "GROQ_API_KEY=xxx,GEMINI_API_KEY=xxx,DRIVE_FOLDER_ID=xxx,CALENDAR_ID=xxx"
```

## Execução Local

```bash
docker build -t secretaria-digital-ia .
docker run -p 8080:8080 \
  -e GROQ_API_KEY=xxx \
  -e GEMINI_API_KEY=xxx \
  secretaria-digital-ia
```

Acesse: `http://localhost:8080`
