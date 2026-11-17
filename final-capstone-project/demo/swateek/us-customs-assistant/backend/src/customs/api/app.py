"""FastAPI app. Scaffold: health only; /chat and the facts routes arrive with the agent graph.

    uv run uvicorn customs.api.app:app --port 3501

Run as a single worker: the one-request gate to the course chat endpoint is per process
(plan §4.6). Starting the app sends nothing to the upgrad endpoints.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from customs import __version__
from customs.config import get_settings
from customs.llm.endpoints import EndpointNotConfigured, validate

settings = get_settings()
app = FastAPI(title="US Customs Assistant", version=__version__)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["content-type"],
)


@app.get("/health")
def health() -> dict:
    try:
        validate(settings)  # keys and certificates present; offline
        endpoints = "configured"
    except EndpointNotConfigured as err:
        endpoints = f"not configured: {err}"
    return {
        "status": "ok",
        "version": __version__,
        "mode": settings.agent_mode,
        "endpoints": endpoints,
        "tracing": bool(settings.langfuse_public_key and settings.langfuse_secret_key),
    }
