"""Chunker: oversized blocks (PDF text, long tables) are split to fit the token budget."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

PATH = Path(__file__).parents[1] / "data" / "rag-corpus" / "chunk_corpus.py"
spec = importlib.util.spec_from_file_location("chunk_corpus", PATH)
cc = importlib.util.module_from_spec(spec)
sys.modules["chunk_corpus"] = cc
spec.loader.exec_module(cc)


def test_pdf_page_without_blank_lines_is_split_under_budget() -> None:
    page = "\n".join(
        f"Line {i} of a PDF page about the rates of duty in column 1 and column 2."
        for i in range(200)
    )
    pieces = cc.split_oversized(page, 100)
    assert len(pieces) > 1 and all(cc.ntok(p) <= 100 for p in pieces)
    assert "\n".join(pieces) == page  # nothing lost or reordered


def test_long_table_repeats_header_in_every_piece() -> None:
    rows = [f"| still wine {i} | $1.07 | per wine gallon |" for i in range(80)]
    table = "\n".join(["| Class | Rate | Per |", "| --- | --- | --- |", *rows])
    pieces = cc.split_oversized(table, 120)
    assert len(pieces) > 1
    assert all(
        p.startswith("| Class | Rate | Per |\n| --- | --- | --- |") for p in pieces
    )


def test_small_block_is_unchanged() -> None:
    assert cc.split_oversized("short text", 350) == ["short text"]
