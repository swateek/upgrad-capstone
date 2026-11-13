"""Generate the report's figures from the saved results (no API calls).

Run from backend/ (matplotlib isn't a project dependency):

    uv run --with matplotlib python ../docs/report/make_figures.py

Writes PNGs to docs/report/figures/. Colours are the validated categorical palette
(slots 1-4: blue, orange, aqua, yellow); identity is never colour alone, since every
series is also in the legend and the numbers are in the report's tables.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

HERE = Path(__file__).resolve().parent
RESULTS = HERE.parent / "results"
OUT = HERE / "figures"

SURFACE = "#ffffff"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#8a8985"
GRID = "#e6e5e1"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
TINT = {"blue": "#e8f0fb", "orange": "#fdeee7", "aqua": "#e5f6ef", "gray": "#f3f2ef"}

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 9,
        "axes.edgecolor": GRID,
        "axes.labelcolor": INK_2,
        "xtick.color": INK_2,
        "ytick.color": INK_2,
        "axes.titlesize": 10,
        "axes.titleweight": "bold",
        "axes.titlecolor": INK,
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.dpi": 200,
    }
)


def load(name: str) -> dict:
    return json.loads((RESULTS / f"{name}.json").read_text())


def style_axes(ax, ylabel: str) -> None:
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.tick_params(axis="both", length=0)


def grouped_bars(ax, groups, series, values, labels_fmt, width=0.26, gap=0.03, label_size=7):
    """values[s][g]; a 2-px-ish surface gap between adjacent bars."""
    n = len(series)
    for s, name in enumerate(series):
        xs = [g + (s - (n - 1) / 2) * width for g in range(len(groups))]
        bars = ax.bar(
            xs,
            values[s],
            width - gap,
            color=SERIES[s],
            label=name,
            edgecolor=SURFACE,
            linewidth=1,
        )
        for b, v in zip(bars, values[s]):
            ax.text(
                b.get_x() + b.get_width() / 2,
                b.get_height() + 0.012,
                labels_fmt(v),
                ha="center",
                va="bottom",
                fontsize=label_size,
                color=INK_2,
            )
    ax.set_xticks(range(len(groups)), groups)


# --- Figure 1: architecture ---------------------------------------------------------------


def box(ax, x, y, w, h, title, body="", fill=TINT["gray"], edge=MUTED, size=7.5):
    """Box in data units (the architecture axes run 0-100 by 0-64)."""
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0,rounding_size=0.8",
            facecolor=fill,
            edgecolor=edge,
            linewidth=1,
        )
    )
    ax.text(
        x + w / 2,
        y + h - 1.2,
        title,
        ha="center",
        va="top",
        fontsize=size,
        fontweight="bold",
        color=INK,
    )
    if body:
        ax.text(
            x + w / 2,
            y + h - 4.0,
            body,
            ha="center",
            va="top",
            fontsize=6.3,
            color=INK_2,
            linespacing=1.4,
        )


def arrow(ax, start, end, label="", style="-|>", color=INK_2, label_xy=None):
    ax.add_patch(
        FancyArrowPatch(start, end, arrowstyle=style, mutation_scale=9, color=color, linewidth=1)
    )
    if label:
        lx, ly = label_xy or ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
        ax.text(
            lx,
            ly,
            label,
            ha="center",
            va="center",
            fontsize=6.2,
            color=INK_2,
            bbox={"facecolor": SURFACE, "edgecolor": "none", "pad": 1},
        )


def fig_architecture() -> None:
    fig, ax = plt.subplots(figsize=(10, 6.4))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 64)
    ax.axis("off")

    # Request path.
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

    # Harness.
    ax.add_patch(
        FancyBboxPatch(
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
        "thinking off; per query: 10 model calls, 10 tool calls,\n40k tokens; 8,192 tokens per call",
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

    # Tools.
    tools = [
        (
            "search_policy",
            "BM25 + dense, RRF (k=60) to top 20\nQwen3-Reranker-8B to top 5\nsource handles mapped in code",
            35,
        ),
        ("screen_vendor", "normalise + RapidFuzz in code\nGeM delist snapshot, 03-Sep-2024", 24.5),
        ("score_bids", "scored in code; gaps, not guesses\nwithholds bidders on a list", 14),
    ]
    for name, body, y in tools:
        box(ax, 78, y, 21, 9.5, name, body, fill=TINT["aqua"], edge=SERIES[2], size=7)
        arrow(ax, (72, 32.5), (78, y + 4.75))

    # Domain pack.
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

    # Services.
    services = [
        ("Qdrant  :3402", "dense vectors\n1,690 by_rule chunks"),
        ("Redis", "retrieval cache\nrate-limit counters"),
        ("SQLite", "checkpointer and\nsession store"),
        ("SiliconFlow", "Qwen3-8B chat, embeddings,\nreranker"),
        ("Langfuse Cloud", "one trace per turn\nPII masked"),
    ]
    w, gap = 18.4, 1.75
    for i, (t, b) in enumerate(services):
        box(ax, 1 + i * (w + gap), 1, w, 9, t, b, size=7)
    arrow(ax, (51, 13), (51, 10), style="<|-|>", color=MUTED)

    fig.savefig(OUT / "fig1-architecture.png", bbox_inches="tight")
    plt.close(fig)


# --- Figure 2: retrieval ------------------------------------------------------------------


def fig_retrieval() -> None:
    chunkers = ["by_rule", "fixed_512", "recursive_800"]
    modes = [
        ("bm25", "BM25"),
        ("dense", "Dense"),
        ("hybrid", "Hybrid (RRF)"),
        ("hybrid_rerank", "Hybrid + rerank"),
    ]
    data = {c: load(f"retrieval-{c}--qwen3-reranker-8b")["recall"] for c in chunkers}
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
        title="chunker (hybrid + rerank uses Qwen3-Reranker-8B)",
        title_fontsize=8,
    )
    fig.savefig(OUT / "fig2-retrieval.png", bbox_inches="tight")
    plt.close(fig)


# --- Figure 3: end-to-end accuracy --------------------------------------------------------


def slice_scores(rows: list[dict]) -> dict[str, float]:
    tally: dict[str, list[int]] = {}
    for r in rows:
        key = "refusal" if r["must_refuse"] else r["job"]
        for k in (key, "all"):
            t = tally.setdefault(k, [0, 0])
            t[0] += r["correct"]
            t[1] += 1
    return {k: c / n for k, (c, n) in tally.items()}


def fig_e2e() -> None:
    runs = [
        ("Run 1", "e2e-v3-run1-rescored"),
        ("Run 2", "e2e-v3-run2-rescored"),
        ("Run 3", "e2e-v3-run3-rescored"),
        ("Run 4", "e2e-v3-run4-rescored"),
        ("Run 5", "e2e-v3-run5-rescored"),
    ]
    slices = [
        ("policy", "Policy (23)"),
        ("screening", "Screening (18)"),
        ("bid", "Bid (11)"),
        ("refusal", "Refusals (8)"),
        ("all", "All 60"),
    ]
    scores = [slice_scores(load(f)["rows"]) for _, f in runs]
    values = [[s[k] for k, _ in slices] for s in scores]
    fig, ax = plt.subplots(figsize=(8.6, 2.6))
    grouped_bars(
        ax,
        [label for _, label in slices],
        [r for r, _ in runs],
        values,
        lambda v: f"{v:.0%}",
        width=0.16,
        gap=0.02,
        label_size=5.6,
    )
    style_axes(ax, "share correct")
    ax.set_ylim(0, 1.12)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.legend(frameon=False, loc="upper left", ncols=5, fontsize=8, bbox_to_anchor=(0, 1.13))
    fig.tight_layout()
    fig.savefig(OUT / "fig3-e2e-accuracy.png", bbox_inches="tight")
    plt.close(fig)


# --- Figure 4: failure taxonomy -----------------------------------------------------------


def fig_failures() -> None:
    runs = [
        ("Run 1", "e2e-v3-run1-rescored"),
        ("Run 2", "e2e-v3-run2-rescored"),
        ("Run 3", "e2e-v3-run3-rescored"),
        ("Run 4", "e2e-v3-run4-rescored"),
        ("Run 5", "e2e-v3-run5-rescored"),
    ]
    labels = ["retrieval miss", "tool-call error", "hallucination", "reasoning error"]
    counts = [Counter(r["failure"] for r in load(f)["rows"] if not r["correct"]) for _, f in runs]
    fig, ax = plt.subplots(figsize=(8.6, 2.5))
    y = list(range(len(runs)))[::-1]
    left = [0] * len(runs)
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
        ax.text(total + 0.2, yy, f"{total} misses", va="center", fontsize=7.5, color=INK_2)
    ax.set_yticks(y, [r for r, _ in runs])
    ax.set_xlabel("questions answered wrongly (of 60)")
    ax.set_xlim(0, 17.5)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=0)
    ax.legend(frameon=False, loc="upper left", ncols=4, fontsize=8, bbox_to_anchor=(0, 1.2))
    fig.tight_layout()
    fig.savefig(OUT / "fig4-failures.png", bbox_inches="tight")
    plt.close(fig)


# --- Figure 5: planner prompt size --------------------------------------------------------


def fig_prompt_size() -> None:
    names = {
        "A_default_deep_agent": "create_deep_agent defaults\n(filesystem tools included)",
        "B_trimmed_todo_plus_subagents": "todo + subagent middleware,\ndefault descriptions",
        "C_trimmed_short_descriptions": "same, short prompts and\ndescriptions (used)",
    }
    builds = [
        (names[c["label"]], c["first_call_prompt_tokens"])
        for c in load("phase0-deepagents-prompt-size")["configs"]
        if c["label"] in names
    ]
    fig, ax = plt.subplots(figsize=(8.6, 1.9))
    y = list(range(len(builds)))[::-1]
    bars = ax.barh(y, [v for _, v in builds], 0.55, color=SERIES[0], edgecolor=SURFACE)
    for b, (_, v) in zip(bars, builds):
        ax.text(
            b.get_width() + 40,
            b.get_y() + b.get_height() / 2,
            f"{v:,} tokens ({v / 8192:.0%} of 8,192)",
            va="center",
            fontsize=7.5,
            color=INK_2,
        )
    ax.set_yticks(y, [n for n, _ in builds])
    ax.set_xlim(0, 4200)
    ax.set_xlabel("prompt tokens on the planner's first call, before any retrieval")
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=0)
    fig.tight_layout()
    fig.savefig(OUT / "fig5-prompt-size.png", bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    fig_architecture()
    fig_retrieval()
    fig_e2e()
    fig_failures()
    fig_prompt_size()
    print("wrote", ", ".join(sorted(p.name for p in OUT.glob("*.png"))))


if __name__ == "__main__":
    main()
