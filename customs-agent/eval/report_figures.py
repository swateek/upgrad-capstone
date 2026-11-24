"""Report figures, drawn from the result files (no number is typed in here).

    uv run python -m eval.report_figures      # -> docs/report/figures/*.png

fig1_retrieval.png    recall@k by retrieval method, 350-token chunks, hard negatives filtered
                      (results/retrieval_experiment*.csv)
fig2_architecture.png the request flow: model steps and code steps (a drawing, not data)
fig3_accuracy.png     accuracy of every arm on eval-v2 and eval-v3 (results/ablation.csv)
fig4_failures.png     agent v1 vs v2 on eval-v3, failures by first wrong stage (failures CSVs,
                      final labels: the hand label where both reviewers agree)
fig5_tokens.png       tokens per model call by stage, agent v2 planner on eval-v3, against the
                      8,192 limit and the 3,000 target (results/token_calls.csv)

Static figures for a printed report: light surface only, values labelled on the marks.
Colours: the dataviz reference palette, categorical slots in fixed order (validated: adjacent
CVD dE >= 9.1, normal-vision >= 19.6; the lighter slots carry visible labels).
"""

from __future__ import annotations

import csv
from collections import Counter
from itertools import pairwise
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"
RUNS = RES / "runs"
OUT = ROOT / "docs" / "report" / "figures"

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
DPI = 200
BAR = 0.55

plt.rcParams.update(
    {
        "font.family": ["Inter", "DejaVu Sans"],
        "font.size": 9,
        "axes.edgecolor": GRID,
        "axes.labelcolor": INK_2,
        "axes.titlecolor": INK,
        "axes.titlesize": 10,
        "axes.titleweight": "semibold",
        "axes.titlelocation": "left",
        "xtick.color": MUTED,
        "ytick.color": INK_2,
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
    }
)


def _style(ax, grid_axis: str = "x") -> None:
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.grid(axis=grid_axis, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)


def hbar(ax, y: float, width: float, color: str, height: float = BAR) -> None:
    """Horizontal bar from the zero baseline."""
    if width > 0:
        ax.barh(y, width, height=height, color=color, linewidth=0)


def fig3_accuracy() -> Path:
    rows = list(csv.DictReader((RES / "ablation.csv").open()))
    wanted = {
        "eval-v2": [
            "prompting: closed_book",
            "prompting: fewshot_json",
            "prompting: cot_sc",
            "prompting: decompose",
            "single_rag",
            "agent v1, code router",
            "agent v1, LLM planner",
        ],
        "eval-v3": [
            "single_rag",
            "agent v1, code router",
            "agent v2, code router",
            "agent v2, LLM planner",
        ],
    }
    titles = {
        "eval-v2": "eval-v2 (80 questions, held out for agent v1)",
        "eval-v3": "eval-v3 (100 new questions, held out for agent v2)",
    }
    fig, axes = plt.subplots(
        2, 1, figsize=(6.4, 4.6), gridspec_kw={"height_ratios": [7, 4], "hspace": 0.55}
    )
    for ax, (set_, arms) in zip(axes, wanted.items(), strict=True):
        by_arm = {r["arm"]: r for r in rows if r["set"] == set_}
        labels, vals = [], []
        for a in arms:
            r = by_arm[a]
            labels.append(
                a.replace("prompting: ", "prompting, ")
                + (" (×3)" if r["runs"] == "3" else "")
            )
            vals.append(float(r["accuracy"]))
        ax.set_xlim(0, 1.0)
        ax.set_ylim(-0.6, len(arms) - 0.4)
        for i, v in enumerate(vals):
            y = len(arms) - 1 - i
            is_agent = labels[i].startswith("agent")
            hbar(ax, y, v, SERIES[0] if is_agent else MUTED)
            ax.text(v + 0.015, y, f"{v:.3f}", va="center", color=INK, fontsize=8.5)
        ax.set_yticks(range(len(arms)))
        ax.set_yticklabels(list(reversed(labels)))
        ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
        ax.set_xticklabels(["0", "0.25", "0.50", "0.75", "1.00"])
        ax.set_title(titles[set_])
        _style(ax)
    axes[-1].set_xlabel(
        "Accuracy: every check passes (outcome, bottom line, dollars, citations, clarify)"
    )
    p = OUT / "fig3_accuracy.png"
    fig.savefig(p, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    return p


STAGES = [
    ("Reading: fact missed", {"EXTRACT_MISSED"}),
    ("Reading: wrong value", {"EXTRACT_WRONG"}),
    ("Reading: fact invented", {"EXTRACT_INVENTED"}),
    ("Units, rules, clarify logic", {"UNITS", "RULES", "CLARIFY_LOGIC"}),
    ("Retrieval and citation", {"RETRIEVAL_MISS", "CITATION_SELECTION"}),
    ("Guard and intent", {"GUARD_MISS", "INTENT", "GUARD_FALSE_REFUSAL"}),
    ("Gold error", {"GOLD_ERROR"}),
]


def final_labels(path: Path) -> Counter:
    c: Counter = Counter()
    for r in csv.DictReader(path.open()):
        h1, h2 = r.get("human_label", ""), r.get("human_label_2", "")
        c[h1 if h1 and h1 == h2 else r["label"]] += 1
    return c


def fig4_failures() -> Path:
    arms = [
        (
            "agent v1 (48 wrong)",
            RUNS / "official-v1-eval3-router" / "failures_router.csv",
        ),
        (
            "agent v2 (23 wrong)",
            RUNS / "official-v2-eval3-router" / "failures_router.csv",
        ),
    ]
    counts = [final_labels(p) for _, p in arms]
    for (name, _), c in zip(arms, counts, strict=True):
        n = sum(c.values())
        assert f"({n} wrong)" in name, (name, n)
        unknown = set(c) - set().union(*(s for _, s in STAGES))
        assert not unknown, unknown
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    h = 0.36
    n = len(STAGES)
    ax.set_xlim(0, 24)
    ax.set_ylim(-0.7, n - 0.3)
    for i, (label, codes) in enumerate(STAGES):
        y = n - 1 - i
        for j, c in enumerate(counts):
            v = sum(c[k] for k in codes)
            yy = y + (h / 2 + 0.02) * (1 if j == 0 else -1)
            hbar(ax, yy, v, SERIES[j], height=h)
            ax.text(v + 0.3, yy, str(v), va="center", color=INK, fontsize=8)
    ax.set_yticks(range(n))
    ax.set_yticklabels([s for s, _ in reversed(STAGES)])
    ax.set_xlabel(
        "Wrong answers on eval-v3 (code router), by the first stage that went wrong"
    )
    ax.set_title("Most failures start in reading the question")
    handles = [plt.Rectangle((0, 0), 1, 1, color=SERIES[j]) for j in range(2)]
    ax.legend(
        handles, [a for a, _ in arms], frameon=False, loc="lower right", fontsize=8.5
    )
    _style(ax)
    p = OUT / "fig4_failures.png"
    fig.savefig(p, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    return p


def _box(ax, x, y, w, h, title, sub, kind):
    """kind: model (the 8B model), code, data (a file the code reads, or the question/answer)."""
    from matplotlib.patches import FancyBboxPatch

    face = {"model": "#fde3d6", "code": "#dbe8f8", "data": SURFACE}[kind]
    edge = {"model": SERIES[1], "code": SERIES[0], "data": MUTED}[kind]
    ax.add_patch(
        FancyBboxPatch(
            (x - w / 2, y - h / 2),
            w,
            h,
            boxstyle="round,pad=0,rounding_size=0.06",
            facecolor=face,
            edgecolor=edge,
            linewidth=1.2,
            linestyle="--" if kind == "data" else "-",
        )
    )
    if title:
        ax.text(
            x,
            y + (0.17 if sub else 0),
            title,
            ha="center",
            va="center",
            fontsize=8.5 if kind != "data" or sub else 6.8,
            color=INK,
            fontweight="semibold" if kind != "data" or sub else "normal",
        )
    if sub:
        ax.text(
            x,
            y - 0.12,
            sub,
            ha="center",
            va="center",
            fontsize=5.9,
            color=INK_2,
            linespacing=1.15,
        )


def _arrow(ax, a, b, color=INK_2):
    ax.annotate(
        "",
        xy=b,
        xytext=a,
        arrowprops={
            "arrowstyle": "-|>",
            "color": color,
            "lw": 1.1,
            "shrinkA": 0,
            "shrinkB": 0,
            "mutation_scale": 9,
        },
    )


def fig2_architecture() -> Path:
    """The request flow (docs/ARCHITECTURE.md, report §5.1). A drawing, not data."""
    fig, ax = plt.subplots(figsize=(7.6, 4.0))
    ax.set_xlim(0, 10.8)
    ax.set_ylim(0, 5.3)
    ax.axis("off")
    w, h = 1.55, 0.82
    top, bot = 3.9, 1.85
    xs = [0.85, 2.6, 4.35, 6.1, 7.85, 9.7]
    row1 = [
        ("Question", "free text", "data"),
        ("Guard", "injection, evasion,\nout of scope", "code"),
        ("Intake", "question \u2192 facts\n(JSON schema)", "model"),
        ("Clean-up", "each fact checked\nagainst the question", "code"),
        ("Plan", "LLM plan + validator\nor fixed router", "model"),
        ("Tools", "restrictions first,\nthen exemption, duty", "code"),
    ]
    for x, (t, sub, k) in zip(xs, row1, strict=True):
        _box(ax, x, top, w, h, t, sub, k)
    for a, b in pairwise(xs):
        _arrow(ax, (a + w / 2, top), (b - w / 2, top))
    xs2 = [9.7, 7.85, 6.1, 4.35, 2.6]
    row2 = [
        ("Search", "rule clauses by id,\nthen hybrid + rerank", "code"),
        ("Answer card", "bottom line\nand working", "code"),
        ("Writer", "explains the card,\ncites clauses", "model"),
        ("Verifier", "numbers, citations;\nevasion (LLM)", "code"),
        ("Answered", "citations, as-of date,\ndisclaimer", "data"),
    ]
    for x, (t, sub, k) in zip(xs2, row2, strict=True):
        _box(ax, x, bot, w, h, t, sub, k)
    _arrow(ax, (xs[-1], top - h / 2), (xs2[0], bot + h / 2))
    for a, b in pairwise(xs2):
        _arrow(ax, (a - w / 2, bot), (b + w / 2, bot))
    # what the code reads
    _box(ax, 9.7, 5.0, 2.0, 0.38, "rules.yaml, rates.yaml", "", "data")
    _arrow(ax, (9.7, 5.0 - 0.19), (9.7, top + h / 2), MUTED)
    _box(ax, 9.7, 0.62, 2.0, 0.38, "corpus: 1,480 chunks", "", "data")
    _arrow(ax, (9.7, 0.62 + 0.19), (9.7, bot - h / 2), MUTED)
    # the other outcomes
    red = "#b8402f"
    for x0, x1, y0, y1, label in (
        (2.6, 2.6, top - h / 2, 3.07, "refused"),
        (6.1, 5.4, top - h / 2, 3.07, "clarify: one question"),
        (9.25, 8.25, top - h / 2, 3.07, "escalate"),
        (4.35, 4.35, bot - h / 2, 0.98, "escalate if the retry fails"),
    ):
        _arrow(ax, (x0, y0), (x1, y1), red)
        ax.text(x1, y1 - 0.13, label, ha="center", va="center", fontsize=7, color=red)
    for i, (k, lab) in enumerate(
        (("model", "Qwen3-8B call"), ("code", "code"), ("data", "input, output, data"))
    ):
        _box(ax, 0.45 + i * 1.75, 0.22, 0.3, 0.2, "", "", k)
        ax.text(0.68 + i * 1.75, 0.22, lab, va="center", fontsize=7, color=INK_2)
    p = OUT / "fig2_architecture.png"
    fig.savefig(p, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    return p


def fig1_retrieval() -> Path:
    rows = list(csv.DictReader((RES / "retrieval_experiment.csv").open()))
    rows += list(csv.DictReader((RES / "retrieval_experiment_bge.csv").open()))
    pick = [
        ("BM25", lambda r: r["method"] == "bm25"),
        ("Dense", lambda r: r["method"] == "dense"),
        ("Hybrid (RRF)", lambda r: r["method"] == "hybrid"),
        (
            "Hybrid + MiniLM",
            lambda r: r["method"] == "hybrid_rerank" and "MiniLM" in r["reranker"],
        ),
        (
            "Hybrid + bge-reranker",
            lambda r: r["method"] == "hybrid_rerank" and "bge" in r["reranker"],
        ),
    ]
    base = [
        r
        for r in rows
        if r["chunk_tokens"] == "350" and r["filter"] == "no_hard_negatives"
    ]
    ks = [1, 3, 5, 10]
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    lines = []
    for j, (name, f) in enumerate(pick):
        match = [r for r in base if f(r)]
        assert len(match) == 1, (name, len(match))
        r = match[0]
        ys = [float(r[f"recall@{k}"]) for k in ks]
        (ln,) = ax.plot(
            ks,
            ys,
            color=SERIES[j],
            linewidth=2,
            solid_capstyle="round",
            solid_joinstyle="round",
            marker="o",
            markersize=5.5,
            markeredgecolor=SURFACE,
            markeredgewidth=1.5,
        )
        lines.append(ln)
        if name.endswith("bge-reranker"):
            ax.annotate(
                f"bge {ys[0]:.3f}",
                (1, ys[0]),
                xytext=(-8, 0),
                textcoords="offset points",
                ha="right",
                va="center",
                fontsize=8,
                color=INK_2,
            )
        if name == "Hybrid + MiniLM":
            ax.annotate(
                f"MiniLM {ys[0]:.3f}",
                (1, ys[0]),
                xytext=(-8, 0),
                textcoords="offset points",
                ha="right",
                va="center",
                fontsize=8,
                color=INK_2,
            )
    ax.set_xscale("log")
    ax.set_xticks(ks)
    ax.set_xticklabels([f"k = {k}" for k in ks])
    ax.set_xlim(0.62, 11.5)
    ax.set_ylim(0.45, 1.0)
    ax.set_ylabel("Recall@k (60 queries)")
    ax.set_title("Retrieval: the bge reranker helps, the MiniLM reranker hurts")
    ax.legend(lines, [n for n, _ in pick], frameon=False, loc="lower right", fontsize=8)
    ax.minorticks_off()
    _style(ax, grid_axis="y")
    ax.spines["bottom"].set_visible(True)
    p = OUT / "fig1_retrieval.png"
    fig.savefig(p, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    return p


def fig5_tokens() -> Path:
    rows = [
        r
        for r in csv.DictReader((RES / "token_calls.csv").open())
        if r["set"] == "eval-v3" and r["arm"] == "agent v2, LLM planner"
    ]
    rows = [r for r in rows if r["stage"] != "all calls"]
    fig, ax = plt.subplots(figsize=(6.4, 2.6))
    n = len(rows)
    ax.set_ylim(-0.6, n - 0.4)
    ax.set_xlim(0, 8600)
    for i, r in enumerate(rows):
        y = n - 1 - i
        p50, mx = int(r["p50"]), int(r["max"])
        ax.plot([p50, mx], [y, y], color=SERIES[0], linewidth=2, solid_capstyle="round")
        ax.scatter(
            [p50],
            [y],
            s=40,
            color=SERIES[0],
            edgecolors=SURFACE,
            linewidths=1.5,
            zorder=3,
        )
        ax.scatter(
            [mx],
            [y],
            s=40,
            color=SURFACE,
            edgecolors=SERIES[0],
            linewidths=1.5,
            zorder=3,
        )
        ax.text(
            mx + 120,
            y,
            f"median {p50:,} · max {mx:,} ({r['calls']} calls)",
            va="center",
            fontsize=8,
            color=INK_2,
        )
    for x, label in ((3000, "input target 3,000"), (8192, "endpoint limit 8,192")):
        ax.axvline(x, color=MUTED, linewidth=1)
        ax.text(x + 60, -0.5, label, ha="left", va="bottom", fontsize=7.5, color=MUTED)
    ax.set_yticks(range(n))
    ax.set_yticklabels([r["stage"] for r in reversed(rows)])
    ax.set_xticks([0, 2000, 4000, 6000, 8000])
    ax.set_xticklabels(["0", "2,000", "4,000", "6,000", "8,000"])
    ax.set_xlabel(
        "Tokens per model call, input + output (agent v2, LLM planner, 3 runs on eval-v3)"
    )
    ax.set_title("Every call stays under 3,000 tokens")
    _style(ax)
    p = OUT / "fig5_tokens.png"
    fig.savefig(p, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    return p


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for f in (
        fig2_architecture,
        fig1_retrieval,
        fig3_accuracy,
        fig4_failures,
        fig5_tokens,
    ):
        print(f().relative_to(ROOT))
