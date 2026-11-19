"""The report's figures, from the saved results (no API calls).

Run from backend/ (matplotlib isn't a project dependency):

    uv run --with matplotlib python ../docs/report/make_figures.py

Reads docs/results/ (official.json, week1_strategies.csv, retrieval_experiment.json) and writes
PNGs to docs/report/figures/. Palette and styling follow the reference app's report; identity
is never colour alone (every series is labelled and the numbers are in the report's tables).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

HERE = Path(__file__).resolve().parent
RESULTS = HERE.parents[0] / "results"
OUT = HERE / "figures"

SURFACE, INK, INK_2, MUTED, GRID = "#ffffff", "#0b0b0b", "#52514e", "#8a8985", "#e6e5e1"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
TINT = {"llm": "#e8f0fb", "code": "#f3f2ef", "rag": "#e5f6ef", "out": "#fdeee7"}

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": GRID,
    "axes.labelcolor": INK_2, "xtick.color": INK_2, "ytick.color": INK_2,
    "axes.titlesize": 10, "axes.titleweight": "bold", "axes.titlecolor": INK,
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.dpi": 200,
})  # fmt: skip

MODES = ["single_rag", "tool_calling", "router", "planner"]


def official() -> dict:
    d = json.loads((RESULTS / "official.json").read_text())
    out = {m: d[m] for m in ("single_rag", "tool_calling", "router")}
    runs = [d[f"planner-{i}"] for i in (1, 2, 3)]
    out["planner"] = {k: sum(r[k] for r in runs) / 3 for k in runs[0]
                      if isinstance(runs[0][k], int | float) and not isinstance(runs[0][k], bool)}  # fmt: skip
    out["planner"]["failures"] = {}
    for r in runs:
        for k, v in r["failures"].items():
            out["planner"]["failures"][k] = out["planner"]["failures"].get(k, 0) + v / 3
    return out


def tidy(ax, ylabel: str = "") -> None:
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def label_bars(ax, bars, fmt="{:.0f}%") -> None:
    for b in bars:
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 1, fmt.format(b.get_height()),
                ha="center", va="bottom", fontsize=7.5, color=INK_2)  # fmt: skip


def fig_architecture() -> None:
    fig, ax = plt.subplots(figsize=(7.2, 3.1))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 44)
    ax.axis("off")
    row1 = [("guard", "code", "evasion,\ninjection"), ("intake", "llm", "facts JSON\n+ grounding"),
            ("prepare", "code", "units, scope"), ("clarify", "code", "one question\nif needed"),
            ("plan", "llm", "planner JSON\n(router fallback)")]  # fmt: skip
    row2 = [("execute", "code", "calculators\n+ search (D20)"), ("audit", "code", "plan-level\nchecks"),
            ("write", "llm", "figures, sources\nby handle"), ("verify", "code", "blocking checks\n+ advisory LLM"),
            ("card", "out", "answered · clarify ·\nrefused · escalated")]  # fmt: skip
    w, h = 16.5, 11

    def box(x, y, name, kind, sub):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.4,rounding_size=1.5",
                                    fc=TINT[kind], ec=MUTED, lw=0.8))  # fmt: skip
        ax.text(x + w / 2, y + h - 3.2, name, ha="center", va="center", fontsize=9,
                fontweight="bold", color=INK)  # fmt: skip
        ax.text(x + w / 2, y + 3.6, sub, ha="center", va="center", fontsize=6.8, color=INK_2)

    def arrow(a, b, style="-|>", color=INK_2, rad=0.0, ls="-"):
        ax.add_patch(FancyArrowPatch(a, b, arrowstyle=style, mutation_scale=9, color=color,
                                     lw=0.9, connectionstyle=f"arc3,rad={rad}", linestyle=ls))  # fmt: skip

    xs = [1 + i * 20 for i in range(5)]
    for x, (n, k, s) in zip(xs, row1, strict=True):
        box(x, 28, n, k, s)
    for x, (n, k, s) in zip(xs, row2, strict=True):
        box(x, 8, n, k, s)
    for i in range(4):
        arrow((xs[i] + w + 0.4, 33.5), (xs[i + 1] - 0.4, 33.5))
        arrow((xs[i] + w + 0.4, 13.5), (xs[i + 1] - 0.4, 13.5))
    # plan -> execute: an elbow between the rows
    mid = 23.5
    ax.plot([xs[4] + w / 2, xs[4] + w / 2, xs[0] + w / 2], [27.6, mid, mid], color=INK_2, lw=0.9)
    arrow((xs[0] + w / 2, mid), (xs[0] + w / 2, 19.4))
    # the two retry paths, as text under their boxes
    ax.text(xs[1] + w / 2, 4.2, "fails → planner once,\nthen escalate", ha="center", va="center",
            fontsize=6.6, color=SERIES[1])  # fmt: skip
    ax.text(xs[3] + w / 2, 4.2, "fails → writer once,\nthen escalate", ha="center", va="center",
            fontsize=6.6, color=SERIES[1])  # fmt: skip
    for i, (k, t) in enumerate([("llm", "model call (Qwen3-8B)"), ("code", "code, no model"),
                                ("out", "answer card")]):  # fmt: skip
        ax.add_patch(FancyBboxPatch((1 + i * 25, 41), 2.5, 2, boxstyle="round,pad=0.1",
                                    fc=TINT[k], ec=MUTED, lw=0.6))  # fmt: skip
        ax.text(4.5 + i * 25, 42, t, fontsize=7, color=INK_2, va="center")
    fig.savefig(OUT / "fig1-architecture.png", bbox_inches="tight")
    plt.close(fig)


def fig_retrieval() -> None:
    v = json.loads((RESULTS / "retrieval_experiment.json").read_text())["variants"]

    def r15(key: str, dev: bool) -> float:
        xs = [x for i, x in v[key].items() if i.startswith("DV") == dev]
        return 100 * sum(x["hit_tok"] is not None and x["hit_tok"] <= 1500 for x in xs) / len(xs)

    rows = [("question only", "window200|hybrid|on|q|off"),
            ("+ rule names", "window200|hybrid|on|qr|off"),
            ("+ topic filter\n(shipped)", "window200|hybrid|on|qr|topic"),
            ("+ cross-encoder\nreranker", "window200|hybrid+ce|on|qr|topic")]  # fmt: skip
    fig, ax = plt.subplots(figsize=(6.4, 2.6))
    x = range(len(rows))
    b1 = ax.bar([i - 0.2 for i in x], [r15(k, True) for _, k in rows], 0.38, color=SERIES[0],
                label="dev (chose)")  # fmt: skip
    b2 = ax.bar([i + 0.2 for i in x], [r15(k, False) for _, k in rows], 0.38, color=SERIES[2],
                label="frozen (reported)")  # fmt: skip
    label_bars(ax, b1)
    label_bars(ax, b2)
    ax.set_xticks(list(x), [n for n, _ in rows])
    ax.set_ylim(0, 100)
    ax.set_title("Gold clause within the first 1,500 tokens of passages (R@1.5k)", loc="left")
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    tidy(ax, "% of claims")
    fig.savefig(OUT / "fig2-retrieval.png", bbox_inches="tight")
    plt.close(fig)


def fig_accuracy() -> None:
    base = [
        b
        for b in csv.DictReader((RESULTS / "week1_strategies.csv").open())
        if b["turn_accuracy_pct"]
    ]  # the four prompting strategies (not the intake rows)
    o = official()
    names = [b["strategy"] for b in base] + MODES
    turn = [float(b["turn_accuracy_pct"]) for b in base] + [
        100 * o[m]["turn_accuracy"] for m in MODES
    ]
    amount = [float(b["amount_accuracy_pct"]) for b in base] + [100 * o[m]["amount_accuracy"]
                                                                  for m in MODES]  # fmt: skip
    fig, ax = plt.subplots(figsize=(7.2, 2.8))
    x = range(len(names))
    b1 = ax.bar([i - 0.2 for i in x], turn, 0.38, color=SERIES[0], label="turns correct")
    b2 = ax.bar(
        [i + 0.2 for i in x], amount, 0.38, color=SERIES[3], label="amount right (answered)"
    )
    label_bars(ax, b1)
    label_bars(ax, b2)
    ax.axvline(3.5, color=MUTED, lw=0.8, ls=":")
    ax.text(1.5, 103, "bare model (week 1)", ha="center", fontsize=7.5, color=INK_2)
    ax.text(5.5, 103, "system modes (official runs)", ha="center", fontsize=7.5, color=INK_2)
    ax.set_xticks(list(x), [n.replace("_", "\n") for n in names], fontsize=7.5)
    ax.set_ylim(0, 110)
    ax.legend(frameon=False, fontsize=8, loc="upper left", bbox_to_anchor=(0, 0.92))
    tidy(ax, "%")
    fig.savefig(OUT / "fig3-accuracy.png", bbox_inches="tight")
    plt.close(fig)


BUCKET = {"retrieval_miss": "Retrieval miss", "invented_figure": "Hallucination",
          "invented_citation": "Hallucination", "unsupported_claim": "Hallucination",
          "tool_failure": "Tool-call error (budget)", "tool_arg_error": "Tool-call error (budget)",
          "repeated_call": "Tool-call error (budget)", "feature_not_built": "Not built (what-if)",
          "infrastructure": "Infrastructure"}  # fmt: skip


def fig_failures() -> None:
    o = official()
    buckets = ["Reasoning error", "Not built (what-if)", "Tool-call error (budget)",
               "Hallucination", "Retrieval miss"]  # fmt: skip
    fig, ax = plt.subplots(figsize=(6.4, 2.6))
    left = [0.0] * len(MODES)
    for i, bk in enumerate(buckets):
        vals = [sum(n for f, n in o[m]["failures"].items() if BUCKET.get(f, "Reasoning error") == bk)
                for m in MODES]  # fmt: skip
        ax.barh(MODES, vals, left=left, color=SERIES[i], label=bk, height=0.6)
        left = [a + b for a, b in zip(left, vals, strict=True)]
    for i, t in enumerate(left):
        ax.text(t + 1, i, f"{t:.0f}", va="center", fontsize=7.5, color=INK_2)
    ax.set_title("Wrong turns out of 91, by template bucket (planner: mean of 3 runs)", loc="left")
    ax.legend(frameon=False, fontsize=7, ncol=3, loc="lower right", bbox_to_anchor=(1, 1.08))
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.savefig(OUT / "fig4-failures.png", bbox_inches="tight")
    plt.close(fig)


def fig_cost() -> None:
    o = official()
    fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.2))
    for ax, (key, title, fmt) in zip(axes, [("model_calls_mean", "Model calls per turn", "{:.1f}"),
                                            ("tokens_mean", "Tokens per turn", "{:,.0f}"),
                                            ("latency_p50", "Latency p50 (s)", "{:.1f}")],
                                     strict=True):  # fmt: skip
        vals = [o[m][key] for m in MODES]
        bars = ax.bar(range(4), vals, color=[SERIES[i] for i in range(4)])
        for b, v in zip(bars, vals, strict=True):
            ax.text(b.get_x() + b.get_width() / 2, v, fmt.format(v), ha="center", va="bottom",
                    fontsize=7, color=INK_2)  # fmt: skip
        ax.set_xticks(range(4), [m.replace("_", "\n") for m in MODES], fontsize=7)
        ax.set_title(title, fontsize=9, loc="left")
        tidy(ax)
    fig.tight_layout()
    fig.savefig(OUT / "fig5-cost.png", bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fig_architecture()
    fig_retrieval()
    fig_accuracy()
    fig_failures()
    fig_cost()
    print(f"wrote {sorted(p.name for p in OUT.glob('*.png'))}")


if __name__ == "__main__":
    main()
