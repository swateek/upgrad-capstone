"""Try search_regulations from the command line (the same search the agent uses)."""

from __future__ import annotations

from src.tools.search_regulations import MAX_K, Args, RegulationSearch


def main() -> int:
    """Try a search from the command line:

    uv run python -m src.retrieval.search "4 bottles of wine after 10 days in Italy" --ids 19cfr148.33
    """
    import argparse

    from src.llm import LLM

    ap = argparse.ArgumentParser(description="search the regulation corpus")
    ap.add_argument("query")
    ap.add_argument("--ids", nargs="*", default=[], help="citation_ids to fetch by id")
    ap.add_argument("-k", type=int, default=MAX_K)
    a = ap.parse_args()
    search = RegulationSearch.from_env(LLM.from_env(run_name="search_cli"))
    out = search(Args(query=a.query, citation_ids=a.ids, k=a.k))
    print(f"{out.method}, {out.ms:.0f} ms; may cite: {', '.join(out.retrieved_ids)}")
    if out.not_found:
        print(f"not found / not citable: {', '.join(out.not_found)}")
    for c in out.clauses:
        how = "by id" if c.found_by == "citation_id" else f"search #{c.rank}"
        print(
            f"\n[{c.citation_id}] {how}, {c.tokens} tokens, {c.authority}, as of {c.as_of}\n  {c.heading}"
        )
        print("  " + " ".join(c.text.split())[:240] + " ...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
