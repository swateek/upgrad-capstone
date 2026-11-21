"""
Reference chunker: turn corpus/**/*.md into corpus/chunks.jsonl.

- Splits on markdown headings first (a chunk never spans two sections),
  then packs paragraphs up to --max-tokens (default 350).
- Never splits a table or a list item in the middle.
- Prefixes each chunk with its heading path so it reads on its own.
- Copies the file's front matter onto every chunk as metadata.

Token counts use tiktoken if installed, else words x 1.35 (close enough
for budgeting against the 8,192-token call limit).

    python chunk_corpus.py
    python chunk_corpus.py --max-tokens 300 --out corpus/chunks.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent

try:
    import tiktoken

    _enc = tiktoken.get_encoding("cl100k_base")

    def ntok(s: str) -> int:
        return len(_enc.encode(s))
except Exception:  # noqa: BLE001 - tiktoken optional; fall back to a word count

    def ntok(s: str) -> int:
        return int(len(s.split()) * 1.35) + 1


def split_front_matter(text: str) -> tuple[dict, str]:
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            meta = yaml.safe_load(text[4:end]) or {}
            return meta, text[end + 4 :].lstrip("\n")
    return {}, text


def blocks(body: str) -> list[str]:
    """Paragraph-level blocks; tables and lists stay whole."""
    out, cur = [], []
    for line in body.splitlines():
        if not line.strip():
            if cur:
                out.append("\n".join(cur))
                cur = []
            continue
        cur.append(line)
    if cur:
        out.append("\n".join(cur))
    return out


def sections(body: str) -> list[tuple[list[str], str]]:
    """[(heading_path, section_text)] split on #, ##, ### headings."""
    path: list[str] = []
    out: list[tuple[list[str], list[str]]] = []
    buf: list[str] = []
    for line in body.splitlines():
        m = re.match(r"^(#{1,3})\s+(.*)", line)
        if m:
            if buf and any(l.strip() for l in buf):
                out.append((path.copy(), buf))
            level, title = len(m.group(1)), m.group(2).strip()
            path = path[: level - 1] + [title]
            buf = []
        else:
            buf.append(line)
    if buf and any(l.strip() for l in buf):
        out.append((path.copy(), buf))
    return [(p, "\n".join(b).strip()) for p, b in out]


def chunk_file(path: Path, max_tokens: int) -> list[dict]:
    meta, body = split_front_matter(path.read_text(encoding="utf-8"))
    doc_id = meta.get("id", path.stem)
    chunks = []
    for head_path, text in sections(body):
        prefix = " > ".join(head_path)
        budget = max_tokens - ntok(prefix) - 4
        cur: list[str] = []
        for b in blocks(text):
            candidate = "\n\n".join(cur + [b])
            if cur and ntok(candidate) > budget:
                chunks.append((prefix, "\n\n".join(cur)))
                cur = [b]
            else:
                cur.append(b)
        if cur:
            chunks.append((prefix, "\n\n".join(cur)))
    out = []
    for n, (prefix, text) in enumerate(chunks, start=1):
        full = f"{prefix}\n\n{text}" if prefix else text
        out.append(
            {
                "chunk_id": f"{doc_id}#{n:03d}",
                "doc_id": doc_id,
                "heading_path": prefix,
                "text": full,
                "tokens": ntok(full),
                "metadata": {k: v for k, v in meta.items() if k != "usage"},
            }
        )
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-tokens", type=int, default=350)
    ap.add_argument("--out", default="corpus/chunks.jsonl")
    args = ap.parse_args()

    files = sorted((ROOT / "corpus").rglob("*.md"))
    all_chunks = []
    for f in files:
        cs = chunk_file(f, args.max_tokens)
        all_chunks.extend(cs)
        over = [c for c in cs if c["tokens"] > args.max_tokens]
        flag = (
            f"  ({len(over)} over budget: a single table or paragraph is too long)"
            if over
            else ""
        )
        print(f"{f.relative_to(ROOT)}: {len(cs)} chunks{flag}")

    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for c in all_chunks:
            fh.write(json.dumps(c, ensure_ascii=False, default=str) + "\n")
    print(f"\n{len(all_chunks)} chunks -> {out}")


if __name__ == "__main__":
    main()
