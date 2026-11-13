"""Load and validate a domain pack's domain.yaml."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict


class CorpusConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manifest: str
    exclusions: str
    splitting: str
    synthetic_dir: str | None = None
    parser: str
    chunkers: list[str]
    default_chunker: str
    metadata_fields: list[str]
    target_docs: tuple[int, int]


class RetrievalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    embedding_model: str
    query_instruction: str | None = None  # task line for instruction-aware query embeddings
    reranker_model: str
    top_k_fused: int = 20
    top_k_final: int = 5


class ToolsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    core: list[str]
    aliases: dict[str, str] = {}
    module: str | None = None


class EvalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    queries: str = "eval/queries.jsonl"
    dev: str = "eval/dev.jsonl"
    retrieval_labels: str = "eval/retrieval_labels.jsonl"
    baseline_jobs: list[str] = []  # which jobs the single-prompt baseline runs on
    baseline_prompt: str = "prompts/baseline.md"


class DomainConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    display_name: str
    ui_modes: list[str]
    corpus: CorpusConfig
    retrieval: RetrievalConfig
    tools: ToolsConfig
    state_fields: list[str]
    eval: EvalConfig = EvalConfig()
    prompts: dict[str, str] = {}  # name -> path in the pack, e.g. answer: prompts/answer.md

    root: Path | None = None

    def path(self, relative: str) -> Path:
        assert self.root is not None
        return self.root / relative


def load_domain(domain_dir: Path) -> DomainConfig:
    raw = yaml.safe_load((domain_dir / "domain.yaml").read_text(encoding="utf-8"))
    cfg = DomainConfig.model_validate(raw)
    if cfg.name != domain_dir.name:
        raise ValueError(f"domain.yaml name '{cfg.name}' does not match folder '{domain_dir.name}'")
    if cfg.corpus.default_chunker not in cfg.corpus.chunkers:
        raise ValueError("corpus.default_chunker must be one of corpus.chunkers")
    cfg.root = domain_dir
    return cfg
