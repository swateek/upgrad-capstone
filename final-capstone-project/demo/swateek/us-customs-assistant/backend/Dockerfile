# syntax=docker/dockerfile:1
# Backend image: the API (uvicorn, single worker) and the one-shot ingest job share it.
# Layout mirrors the repo so PROJECT_ROOT resolves to /app:
#   /app/backend (code)   /app/pack (mounted read-only)   /app/certs (read-only)   /app/data (volume)
FROM ghcr.io/astral-sh/uv:0.9.18 AS uv

FROM python:3.12.15-slim-bookworm
COPY --from=uv /uv /usr/local/bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_HTTP_TIMEOUT=300 \
    HF_HOME=/opt/hf \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app/backend

# Dependencies first (cached layer), then the project itself.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY eval ./eval
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

# Bake the tokenizers (tokenizer.json only, no weights): Qwen3 for the budget guard and the
# listwise reranker, bge-small for cutting chunks to the embedding endpoint's 512 tokens.
RUN python -c "from tokenizers import Tokenizer; [Tokenizer.from_pretrained(m) for m in ('Qwen/Qwen3-8B', 'BAAI/bge-small-en-v1.5')]"

RUN useradd --create-home --uid 10001 app && mkdir -p /app/data /app/docs/results \
    && chown -R app /app/data /app/docs /opt/hf
USER app

EXPOSE 8000
# One worker: the gate that keeps one active request on the course key is per process.
CMD ["uvicorn", "customs.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
