FROM python:3.11-slim

# Instala ffmpeg — CRÍTICO para separação de canais de áudio estéreo
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Porta padrão do Cloud Run
ENV PORT=8080

# Healthcheck para Cloud Run
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8080/_stcore/health || exit 1

EXPOSE 8080

CMD ["streamlit", "run", "app.py", \
     "--server.port=8080", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--server.enableCORS=false", \
     "--server.enableXsrfProtection=false", \
     "--server.maxUploadSize=200", \
     "--browser.gatherUsageStats=false"]
