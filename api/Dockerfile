# StackSense API — FastAPI serving layer.
# Artifacts (data/) are baked into the image: ~32MB total, small enough that a
# volume mount would only add complexity for no benefit. Rebuild the image to
# ship new artifacts.

FROM python:3.12-slim

WORKDIR /app

# System deps for pdfplumber (relies on some C libs via its own deps) and to
# keep torch happy without the full build toolchain.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code first (changes often), then data (changes rarely) — order doesn't
# matter much at this size, but keeps the layer cache sane if data grows.
COPY api.py resume_analyze.py ./
COPY data/ ./data/

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0) if urllib.request.urlopen('http://localhost:8000/health').status==200 else sys.exit(1)"

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
