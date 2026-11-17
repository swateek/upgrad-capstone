# HR policy domain pack (template)

This folder is empty on purpose. It shows what a second domain needs. The core code doesn't change. Mirror `../procurement/`:

| Path | What to put there |
|---|---|
| `domain.yaml` | `name: hr_policy`, `display_name`, `ui_modes`, corpus/chunker settings, embedding and reranker models, tools, `state_fields` |
| `corpus/manifest.yaml` | One entry per HR policy file: id, store, instrument, URL, source page, edition, edition date, language |
| `corpus/exclusions.yaml` | Superseded or out-of-scope sources that must never be indexed |
| `corpus/editions.md` | Which edition was kept when sources disagree, and why |
| `prompts/` | Planner, executor, critic, and baseline prompts for HR questions. Few-shot examples come from `eval/dev.jsonl`. |
| `tools.py` | Optional HR-specific tools (e.g. a leave-balance calculator). The core `search_docs` tool works without this file. |
| `refusals.yaml` | What the HR assistant must decline, and the wording |
| `critic_rules.py` | Deterministic checks for HR answers |
| `eval/queries.jsonl`, `eval/dev.jsonl`, `eval/retrieval_labels.jsonl` | The frozen eval set, the dev set, and the retrieval labels |

To switch:

```bash
DOMAIN=hr_policy uv run python -m copilot.ingest.download --freeze
DOMAIN=hr_policy docker compose --profile ingest run ingest
DOMAIN=hr_policy docker compose up
```
