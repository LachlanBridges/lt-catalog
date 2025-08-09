FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libx11-6 libxcb1 libxcomposite1 libxcursor1 libxdamage1 \
    libxext6 libxfixes3 libxi6 libxtst6 libcups2 libdrm2 libxrandr2 \
    libgbm1 libpango-1.0-0 libcairo2 libasound2 libatk1.0-0 libatk-bridge2.0-0 \
    wget ca-certificates git \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install --with-deps chromium

COPY . .

# Default data root inside container; override by mounting volume and/or env
ENV LIBRARY_DATA_DIR=/app/data

# Ensure runtime dirs exist at build time (harmless at run)
RUN python - <<'PY'
from library_data.config import ensure_dirs
ensure_dirs()
PY

# Default command shows available CLIs
CMD ["python", "-c", "import sys;print('CLIs: library-data-ingest, library-data-enrich-levels, library-data-export-lt, library-data-capture-state'); print('Set LIBRARY_DATA_DIR or mount ./library-data as a volume.');"]
