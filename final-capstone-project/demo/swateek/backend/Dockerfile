# Backend image: API (uvicorn) and the one-shot ingest job share it.
# Layout mirrors the repo so PROJECT_ROOT resolves to /app:
#   /app/backend (code)   /app/domains (mounted read-only)   /app/data (volume)
FROM ghcr.io/astral-sh/uv:0.9.18 AS uv

FROM python:3.12.15-slim-bookworm
COPY --from=uv /uv /usr/local/bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    HF_HOME=/opt/hf \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app/backend

# Dependencies first (cached layer), then the project itself.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY eval ./eval
RUN uv sync --frozen --no-dev

# Bake the Qwen3 tokenizer (tokenizer.json only, no weights) so the budget guard works offline.
RUN python -c "from tokenizers import Tokenizer; Tokenizer.from_pretrained('Qwen/Qwen3-8B')"

RUN useradd --create-home --uid 10001 app && mkdir -p /app/data /app/docs/results \
    && chown -R app /app/data /app/docs /opt/hf
USER app

EXPOSE 8000
CMD ["uvicorn", "copilot.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
