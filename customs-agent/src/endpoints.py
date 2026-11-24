"""Endpoint settings and TLS-aware OpenAI clients.

Each endpoint (chat, embeddings) has its own URL, API key and CA certificate,
read from environment variables or `.env`:

    CHAT_BASE_URL, CHAT_API_KEY, CHAT_CA_CERT, CHAT_MODEL
    EMBED_BASE_URL, EMBED_API_KEY, EMBED_CA_CERT, EMBED_MODEL
    optional: <PREFIX>_CLIENT_CERT, <PREFIX>_CLIENT_KEY (mutual TLS),
              CA_RELAX_STRICT=1 (Python 3.13+ strict X.509 check off)

This is the library copy of the helpers first written in
`prechecks/check_endpoint.py`; application code imports from here.
"""

from __future__ import annotations

import os
import ssl
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from openai import DefaultHttpxClient, OpenAI

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # customs-agent/


class ConfigError(RuntimeError):
    """A required setting or file is missing or unreadable."""


def load_env() -> Path | None:
    """Load `.env` (searched upwards from the current folder). Returns its folder, if found."""
    try:
        from dotenv import find_dotenv, load_dotenv
    except ImportError:
        return None
    env_file = find_dotenv(usecwd=True) or (
        str(PROJECT_ROOT / ".env") if (PROJECT_ROOT / ".env").is_file() else ""
    )
    if not env_file:
        return None
    load_dotenv(env_file)
    return Path(env_file).resolve().parent


def resolve_file(
    value: str | None, setting: str, env_dir: Path | None = None
) -> str | None:
    """Find a certificate/key file named by a setting.

    Relative paths are tried against the current folder, the `.env` folder and
    `customs-agent/`. Raises ConfigError listing what was tried.
    """
    if not value:
        return None
    raw = Path(os.path.expanduser(value.strip().strip('"').strip("'")))
    if raw.is_absolute():
        candidates = [raw]
    else:
        bases = [Path.cwd()] + ([env_dir] if env_dir else []) + [PROJECT_ROOT]
        candidates = list(dict.fromkeys((b / raw).resolve() for b in bases))
    for c in candidates:
        if c.is_file():
            return str(c)
    tried = ", ".join(str(c) for c in candidates)
    raise ConfigError(f"{setting}: file not found: {value} (tried: {tried})")


def load_ca(ctx: ssl.SSLContext, path: str) -> None:
    """Trust a CA file whatever its extension: PEM (text) or DER (binary)."""
    data = Path(path).read_bytes()
    if b"-----BEGIN CERTIFICATE-----" in data:
        ctx.load_verify_locations(cafile=path)
    else:
        try:
            ctx.load_verify_locations(cadata=data)
        except ssl.SSLError as e:
            raise ConfigError(
                f"Could not read CA certificate {path} as PEM or DER: {e}"
            ) from e


@dataclass(frozen=True)
class Endpoint:
    """Connection settings for one endpoint. `api_key` is never printed (repr hides it)."""

    name: str  # "chat" or "embeddings"
    base_url: str
    api_key: str
    model: str | None = None
    ca_cert: str | None = None
    client_cert: str | None = None
    client_key: str | None = None

    def __repr__(self) -> str:  # keep the key out of logs and tracebacks
        return (
            f"Endpoint(name={self.name!r}, host={self.host!r}, model={self.model!r}, "
            f"ca_cert={self.ca_cert and Path(self.ca_cert).name!r})"
        )

    @property
    def host(self) -> str:
        return urlparse(self.base_url).netloc or self.base_url

    @classmethod
    def from_env(cls, name: str, prefix: str, env_dir: Path | None = None) -> Endpoint:
        base_url = os.environ.get(f"{prefix}_BASE_URL")
        api_key = os.environ.get(f"{prefix}_API_KEY")
        if not base_url or not api_key:
            raise ConfigError(
                f"Set {prefix}_BASE_URL and {prefix}_API_KEY for the {name} endpoint."
            )
        return cls(
            name=name,
            base_url=base_url,
            api_key=api_key,
            model=os.environ.get(f"{prefix}_MODEL") or None,
            ca_cert=resolve_file(
                os.environ.get(f"{prefix}_CA_CERT"), f"{prefix}_CA_CERT", env_dir
            ),
            client_cert=resolve_file(
                os.environ.get(f"{prefix}_CLIENT_CERT"),
                f"{prefix}_CLIENT_CERT",
                env_dir,
            ),
            client_key=resolve_file(
                os.environ.get(f"{prefix}_CLIENT_KEY"), f"{prefix}_CLIENT_KEY", env_dir
            ),
        )


def make_client(ep: Endpoint, timeout: float = 120.0) -> OpenAI:
    """OpenAI-compatible client that trusts the endpoint's CA.

    The client's own retries are off (max_retries=0): src/llm.py owns retry
    and back-off so every attempt is queued and logged.
    """
    http_client = None
    if ep.ca_cert or ep.client_cert:
        ctx = ssl.create_default_context()
        if ep.ca_cert:
            load_ca(ctx, ep.ca_cert)
        if os.environ.get("CA_RELAX_STRICT") == "1" and hasattr(
            ssl, "VERIFY_X509_STRICT"
        ):
            ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
        if ep.client_cert:
            ctx.load_cert_chain(certfile=ep.client_cert, keyfile=ep.client_key or None)
        http_client = DefaultHttpxClient(verify=ctx)
    return OpenAI(
        base_url=ep.base_url,
        api_key=ep.api_key,
        max_retries=0,
        timeout=timeout,
        http_client=http_client,
    )
