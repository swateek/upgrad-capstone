# DeclareRight web app: FastAPI serving the built React app, in one container (SETUP.md step 13).
#
#   docker compose up --build            # http://localhost:8000
#
# Baked in: the code, rules.yaml / rates.yaml, the built web app, and the search corpus
# (chunks.jsonl + the saved index, which must exist before the build: SETUP.md steps 5 and 9).
# Never baked in: .env, certs/, logs/ (mounted at run time by docker-compose.yml).
# The reranker (~2 GB) downloads on the first question into a volume; build with
# --build-arg PRELOAD_RERANKER=1 to put it in the image instead (for a deploy with no volume).

# ---------------------------------------------------------------- 1. web app (React + Vite)
FROM node:20-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# ---------------------------------------------------------------- 2. API (Python 3.12 + uv)
FROM python:3.12-slim AS app
ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app

# Dependencies first (cached while only the code changes), installed offline from docker/wheels/,
# which `uv run python docker/fetch_wheels.py` fills on the host: every package at its uv.lock
# version for Linux, PyTorch as the CPU-only build (the PyPI one pulls several GB of NVIDIA CUDA
# packages a container without an NVIDIA GPU cannot use). Docker Desktop reached PyPI at ~28 KB/s
# on the owner's Mac, so the build does not download anything itself. The wheels are mounted for
# this step only, not copied into the image.
RUN --mount=type=bind,source=docker/wheels,target=/wheels \
    set -eu; \
    test -f /wheels/requirements.txt || { echo "docker/wheels is empty: run 'uv run python docker/fetch_wheels.py' first (SETUP.md step 13)"; exit 1; }; \
    uv venv /app/.venv; \
    uv pip install --python /app/.venv --no-index --find-links /wheels -r /wheels/requirements.txt

COPY src/ src/
COPY app/ app/
COPY data/rules.yaml data/rates.yaml data/
COPY data/rag-corpus/chunk_corpus.py data/rag-corpus/
COPY data/rag-corpus/corpus/chunks.jsonl data/rag-corpus/corpus/
COPY data/rag-corpus/index/ data/rag-corpus/index/
COPY --from=web /web/dist web/dist

# The model cache folder must exist, owned by the app user, before compose mounts the hf-cache
# volume there: a new volume copies the folder's owner, and a missing folder comes out owned by
# root, so the reranker download fails with "Permission denied".
RUN useradd --create-home --uid 1000 app \
    && mkdir -p logs certs /home/app/.cache/huggingface \
    && chown -R app:app /app /home/app
USER app
ENV PATH=/app/.venv/bin:$PATH \
    HF_HOME=/home/app/.cache/huggingface \
    STATE_RULES=all

ARG PRELOAD_RERANKER=0
RUN if [ "$PRELOAD_RERANKER" = "1" ]; then \
      python -c "from sentence_transformers import CrossEncoder; CrossEncoder('BAAI/bge-reranker-v2-m3')"; \
    fi

EXPOSE 8000
# /api/live answers without loading the models, so the check passes while the first question warms up
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/live', timeout=4)"
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
