# ── Imagem de build ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# Instala dependencias de sistema necessarias para psycopg2-binary
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ── Imagem final (menor) ──────────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Dependencias de runtime:
# - libpq5: psycopg2-binary
# - tesseract-ocr + tesseract-ocr-por: OCR para PDFs digitalizados (PR6 #3, Guia v3 §2.7)
# - poppler-utils: pdf2image precisa do `pdftoppm`/`pdftocairo` para converter PDF -> imagem
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    tesseract-ocr \
    tesseract-ocr-por \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Copia pacotes instalados do builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copia codigo da aplicacao (sem .venv, __pycache__, .env local)
COPY . .

# Porta padrao do uvicorn
EXPOSE 8000

# Usuario nao-root para reducao de superficie de ataque
RUN adduser --disabled-password --gecos "" appuser \
    && chown -R appuser:appuser /app
USER appuser

# Healthcheck interno — Railway e outros orquestradores usam isso
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
