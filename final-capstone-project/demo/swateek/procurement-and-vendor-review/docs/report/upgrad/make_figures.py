"""Generate the upgrad report's figures from the saved results (no API calls).

Run from backend/ (matplotlib isn't a project dependency):

    uv run --with matplotlib python ../docs/report/upgrad/make_figures.py

Writes PNGs to docs/report/upgrad/figures/. Styling and the plotting helpers come from
docs/report/siliconflow/make_figures.py, which is imported, not changed; that report's figures stay as they
are. Series colours follow a fixed order: SiliconFlow first, then the upgrad runs.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE.parents[1] / "results"
OUT = HERE / "figures"

_spec = importlib.util.spec_from_file_location(
    "base_figures", HERE.parent / "siliconflow" / "make_figures.py"
)
base = importlib.util.module_from_spec(_spec)
sys.dont_write_bytecode = True  # no __pycache__ in the siliconflow folder
_spec.loader.exec_module(base)
base.OUT = (
    OUT  # base helpers that save a figure write here, never to docs/report/siliconflow/figures
)

plt = base.plt
SERIES, SURFACE, INK, INK_2, MUTED, GRID, TINT = (
    base.SERIES,
    base.SURFACE,
    base.INK,
    base.INK_2,
    base.MUTED,
    base.GRID,
    base.TINT,
)
box, arrow, grouped_bars, style_axes = base.box, base.arrow, base.grouped_bars, base.style_axes

# The runs compared throughout: SiliconFlow's final run, then the two upgrad runs.
RUNS = [
    ("SiliconFlow run 5", "siliconflow/e2e-v3-run5-rescored"),
    ("upgrad run 1", "upgrad/e2e-v3-run1"),
    ("upgrad run 2", "upgrad/e2e-v3-run2"),
]


def load(name: str) -> dict:
    return json.loads((RESULTS / f"{name}.json").read_text())


# --- Figure 1: architecture on the course endpoints ---------------------------------------


def fig_architecture() -> None:
    fig, ax = plt.subplots(figsize=(10, 6.4))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 64)
    ax.axis("off")

    box(
        ax,
        2,
        50,
        20,
        13,
        "Web  :3400",
        "Next.js + assistant-ui\nAssistant chat, live trace\nPolicy, Vendor, Bid modes\nDRAFT on every answer",
    )
    box(
        ax,
        30,
        50,
        26,
        13,
        "API  :3401  (FastAPI)",
        "rate limits per IP and conversation\n/chat streams progress (SSE),\nanswer only after the critic\nno award, order or debar route",
    )
    arrow(ax, (22, 56.5), (30, 56.5), style="<|-|>")

    ax.add_patch(
        base.FancyBboxPatch(
            (28, 13),
            46,
            33,
            boxstyle="round,pad=0,rounding_size=1",
            facecolor=SURFACE,
            edgecolor=SERIES[0],
            linewidth=1.2,
            linestyle="--",
        )
    )
    ax.text(
        38.5,
        44.8,
        "Deep Agents harness  (Qwen3-8B)",
        fontsize=7.5,
        fontweight="bold",
        color=SERIES[0],
        va="top",
    )
    ax.text(
        38.5,
        42.0,
        "thinking off; per query: 10 model calls, 10 tool calls,\n40k tokens (rerank included); "
        "one request at a time",
        fontsize=6.2,
        color=INK_2,
        va="top",
    )
    box(ax, 30, 27, 12, 11, "Refusal check", "patterns in code,\nbefore planning", size=7)
    box(ax, 45, 27, 11, 11, "Planner", "write_todos\nand task", fill=TINT["blue"], size=7)
    box(ax, 59, 27, 13, 11, "Executor", "subagent with\nthe three tools", fill=TINT["blue"], size=7)
    box(
        ax,
        45,
        15,
        27,
        9.5,
        "Critic gate (code)",
        "deterministic checks block; LLM notes advisory\nup to 2 revisions, then release",
        fill=TINT["orange"],
        edge=SERIES[1],
        size=7,
    )
    arrow(ax, (36, 50), (36, 38))
    arrow(ax, (42, 32.5), (45, 32.5))
    arrow(ax, (56, 32.5), (59, 32.5))
    arrow(ax, (68, 27), (68, 24.5), label="draft", label_xy=(70.5, 25.8))
    arrow(ax, (62, 24.5), (62, 27), label="revise", label_xy=(59.3, 25.8))

    tools = [
        (
            "search_policy",
            (
                "BM25 + bge-small, RRF to top 20\nQwen3-8B listwise to top 5\n"
                "source handles mapped in code"
            ),
            35,
        ),
        ("screen_vendor", "normalise + RapidFuzz in code\nGeM delist snapshot, 03-Sep-2024", 24.5),
        ("score_bids", "scored in code; gaps, not guesses\nwithholds bidders on a list", 14),
    ]
    for name, body, y in tools:
        box(ax, 78, y, 21, 9.5, name, body, fill=TINT["aqua"], edge=SERIES[2], size=7)
        arrow(ax, (72, 32.5), (78, y + 4.75))

    box(
        ax,
        2,
        13,
        20,
        33,
        "Domain pack",
        "domains/procurement/\n\ncorpus manifest + hash lock\ntools.py, screening.py\nprompts/, critic_rules.py\n"
        "refusal_patterns.yaml\nbid cases, screening CSVs\nfrozen eval set\n\n"
        "switch domain:\nDOMAIN=<name> + re-ingest",
        size=7,
    )
    arrow(ax, (22, 32.5), (28, 32.5), color=MUTED, label="loads", label_xy=(25, 34.5))

    services = [
        ("Qdrant  :3402", "bge-small, 384-d\n1,690 chunks, 2,489 windows"),
        ("Redis", "retrieval cache\nrate-limit counters"),
        ("SQLite", "checkpointer and\nsession store"),
        ("Course endpoints", "Qwen3-8B chat + rerank (1033)\nbge-small embeddings (1035)"),
        ("Langfuse Cloud", "one trace per turn\nPII masked"),
    ]
    w, gap = 18.4, 1.75
    for i, (t, b) in enumerate(services):
        box(ax, 1 + i * (w + gap), 1, w, 9, t, b, size=7)
    arrow(ax, (51, 13), (51, 10), style="<|-|>", color=MUTED)

    fig.savefig(OUT / "fig1-architecture.png", bbox_inches="tight")
    plt.close(fig)


# --- Figure 2: retrieval, SiliconFlow stack vs course stack (by_rule, eval v3 labels) -----


def fig_retrieval() -> None:
    stacks = [
        (
            "SiliconFlow: Qwen3-Embedding-0.6B + Qwen3-Reranker-8B",
            "siliconflow/retrieval-by_rule--qwen3-reranker-8b--eval-v3",
        ),
        (
            "upgrad: bge-small-en-v1.5 + Qwen3-8B listwise",
            "upgrad/retrieval-by_rule--qwen3-8b-listwise",
        ),
    ]
    modes = ["bm25", "dense", "hybrid", "hybrid_rerank"]
    data = [load(f)["recall"] for _, f in stacks]
    fig, axes = plt.subplots(1, 2, figsize=(9.6, 3.2), sharey=True)
    for ax, k in zip(axes, ("recall@1", "recall@5")):
        values = [[d[m][k] for m in modes] for d in data]
        grouped_bars(
            ax,
            ["BM25", "Dense", "Hybrid\n(RRF)", "Hybrid\n+ rerank"],
            [s for s, _ in stacks],
            values,
            lambda v: f"{v:.2f}",
            width=0.36,
            label_size=6.5,
        )
        ax.set_title(k, loc="left")
        style_axes(ax, "share of 38 questions" if k == "recall@1" else "")
        ax.set_ylim(0, 1.12)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    fig.legend(handles, labels, frameon=False, loc="upper center", ncols=1, fontsize=8)
    fig.savefig(OUT / "fig2-retrieval.png", bbox_inches="tight")
    plt.close(fig)


def fig_chunkers() -> bool:
    """Only when the bge chunking comparison has been run (all three files present)."""
    chunkers = ["by_rule", "fixed_512", "recursive_800"]
    files = [RESULTS / f"upgrad/retrieval-{c}--qwen3-8b-listwise.json" for c in chunkers]
    if not all(f.exists() for f in files):
        return False
    modes = [
        ("bm25", "BM25"),
        ("dense", "Dense"),
        ("hybrid", "Hybrid (RRF)"),
        ("hybrid_rerank", "Hybrid + rerank"),
    ]
    data = {c: json.loads(f.read_text())["recall"] for c, f in zip(chunkers, files)}
    fig, axes = plt.subplots(1, 2, figsize=(9.6, 3.2), sharey=True)
    for ax, k in zip(axes, ("recall@1", "recall@5")):
        values = [[data[c][m][k] for m, _ in modes] for c in chunkers]
        grouped_bars(
            ax,
            ["BM25", "Dense", "Hybrid\n(RRF)", "Hybrid\n+ rerank"],
            chunkers,
            values,
            lambda v: f"{v:.2f}",
            label_size=6.2,
        )
        ax.set_title(k, loc="left")
        style_axes(ax, "share of 38 questions" if k == "recall@1" else "")
        ax.set_ylim(0, 1.1)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    fig.legend(
        handles,
        labels,
        frameon=False,
        loc="upper center",
        ncols=3,
        fontsize=8,
        title="chunker (bge-small-en-v1.5; rerank: Qwen3-8B listwise)",
        title_fontsize=8,
    )
    fig.savefig(OUT / "fig2b-chunkers.png", bbox_inches="tight")
    plt.close(fig)
    return True


# --- Figure 3: end-to-end accuracy ---------------------------------------------------------


def fig_e2e() -> None:
    slices = [
        ("policy", "Policy (23)"),
        ("screening", "Screening (18)"),
        ("bid", "Bid (11)"),
        ("refusal", "Refusals (8)"),
        ("all", "All 60"),
    ]
    scores = [base.slice_scores(load(f)["rows"]) for _, f in RUNS]
    values = [[s[k] for k, _ in slices] for s in scores]
    fig, ax = plt.subplots(figsize=(8.6, 2.6))
    grouped_bars(
        ax,
        [label for _, label in slices],
        [r for r, _ in RUNS],
        values,
        lambda v: f"{v:.0%}",
        width=0.26,
        gap=0.03,
        label_size=6,
    )
    style_axes(ax, "share correct")
    ax.set_ylim(0, 1.12)
    ax.yaxis.set_major_formatter(base.matplotlib.ticker.PercentFormatter(1.0))
    ax.legend(frameon=False, loc="upper left", ncols=3, fontsize=8, bbox_to_anchor=(0, 1.13))
    fig.tight_layout()
    fig.savefig(OUT / "fig3-e2e-accuracy.png", bbox_inches="tight")
    plt.close(fig)


# --- Figure 4: failure taxonomy ------------------------------------------------------------


def fig_failures() -> None:
    labels = ["retrieval miss", "tool-call error", "hallucination", "reasoning error"]
    counts = [Counter(r["failure"] for r in load(f)["rows"] if not r["correct"]) for _, f in RUNS]
    fig, ax = plt.subplots(figsize=(8.6, 1.9))
    y = list(range(len(RUNS)))[::-1]
    left = [0] * len(RUNS)
    for i, lab in enumerate(labels):
        widths = [c.get(lab, 0) for c in counts]
        ax.barh(
            y, widths, 0.55, left=left, color=SERIES[i], label=lab, edgecolor=SURFACE, linewidth=1.5
        )
        for yy, lft, wd in zip(y, left, widths):
            if wd:
                ax.text(
                    lft + wd / 2, yy, str(wd), ha="center", va="center", fontsize=7.5, color=INK
                )
        left = [a + b for a, b in zip(left, widths)]
    for yy, total in zip(y, left):
        ax.text(total + 0.15, yy, f"{total} misses", va="center", fontsize=7.5, color=INK_2)
    ax.set_yticks(y, [r for r, _ in RUNS])
    ax.set_xlabel("questions answered wrongly (of 60)")
    ax.set_xlim(0, max(left) + 3)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=0)
    ax.legend(frameon=False, loc="upper left", ncols=4, fontsize=8, bbox_to_anchor=(0, 1.3))
    fig.tight_layout()
    fig.savefig(OUT / "fig4-failures.png", bbox_inches="tight")
    plt.close(fig)


# --- Figure 6: tokens per task -------------------------------------------------------------


def fig_tokens() -> None:
    parts = [("chat_tokens", "agent (planner, executor, critic)"), ("rerank_tokens", "rerank")]
    runs = [(name, load(f)["rows"]) for name, f in RUNS]
    fig, ax = plt.subplots(figsize=(8.6, 1.9))
    y = list(range(len(runs)))[::-1]
    left = [0.0] * len(runs)
    for i, (key, lab) in enumerate(parts):
        widths = [sum(r[key] for r in rows) / len(rows) for _, rows in runs]
        ax.barh(
            y, widths, 0.55, left=left, color=SERIES[i], label=lab, edgecolor=SURFACE, linewidth=1.5
        )
        for yy, lft, wd in zip(y, left, widths):
            ax.text(
                lft + wd / 2, yy, f"{wd:,.0f}", ha="center", va="center", fontsize=7.5, color=INK
            )
        left = [a + b for a, b in zip(left, widths)]
    for yy, total in zip(y, left):
        ax.text(total + 150, yy, f"{total:,.0f} per task", va="center", fontsize=7.5, color=INK_2)
    ax.set_yticks(y, [name for name, _ in runs])
    ax.set_xlabel("mean tokens per task (all 60 questions; rerank runs only on policy searches)")
    ax.set_xlim(0, max(left) * 1.25)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=0)
    ax.legend(frameon=False, loc="upper left", ncols=2, fontsize=8, bbox_to_anchor=(0, 1.3))
    fig.tight_layout()
    fig.savefig(OUT / "fig6-tokens.png", bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    fig_architecture()
    fig_retrieval()
    fig_chunkers()
    fig_e2e()
    fig_failures()
    fig_tokens()
    base.fig_prompt_size()  # SiliconFlow measurement, same weights and chat template
    print("wrote", ", ".join(sorted(p.name for p in OUT.glob("*.png"))))


if __name__ == "__main__":
    main()
