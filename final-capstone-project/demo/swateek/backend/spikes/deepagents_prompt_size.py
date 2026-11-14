"""Phase 0 spike: how many prompt tokens does a Deep Agents harness spend before any work?

Offline. A stub chat model records exactly what the harness would send (system prompt, messages,
tool schemas) and answers "done". No API calls, no credit used.

    uv run python spikes/deepagents_prompt_size.py

Measures the main agent's first model call for:
  A. create_deep_agent defaults + 3 placeholder tools + executor/critic subagents
  B. a trimmed stack: create_agent + TodoListMiddleware + SubAgentMiddleware (no filesystem,
     no general-purpose subagent), short prompts

Tool bodies are placeholders; only their schemas matter here. Writes
docs/results/siliconflow/phase0-deepagents-prompt-size.json.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, convert_to_openai_messages
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import Field

from copilot.config import PROJECT_ROOT, get_settings
from copilot.llm.budget import count_message_tokens, get_tokenizer

CAPTURED: list[dict[str, Any]] = []


class CaptureModel(BaseChatModel):
    """Records the request instead of calling a provider."""

    bound_tools: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "capture"

    def bind_tools(self, tools, **kwargs):
        return self.model_copy(update={"bound_tools": [convert_to_openai_tool(t) for t in tools]})

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        CAPTURED.append(
            {"messages": convert_to_openai_messages(messages), "tools": list(self.bound_tools)}
        )
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="done"))])


@tool
def search_policy(query: str, instrument: str | None = None) -> str:
    """Search the policy index. Returns clauses with doc_id and rule_id."""
    return "[]"


@tool
def screen_vendor(name: str) -> str:
    """Look up a firm name in the dated vendor screening snapshot."""
    return "{}"


@tool
def score_bids(case_id: str) -> str:
    """Load a preloaded bid case and return a draft score sheet."""
    return "{}"


TOOLS = [search_policy, screen_vendor, score_bids]
SHORT_PLANNER = (
    "You plan procurement questions. Write at most 4 todos, then delegate each to the "
    "executor with the task tool. Never award, order, or debar."
)
SUBAGENTS = [
    {
        "name": "executor",
        "description": "Runs search_policy, screen_vendor, score_bids and drafts a cited answer.",
        "system_prompt": "Use the tools. Cite doc_id:rule_id for every factual sentence.",
        "tools": TOOLS,
    },
    {
        "name": "critic",
        "description": "Checks a draft answer for citations, weights and banned wording.",
        "system_prompt": "Return PASS or a list of problems. Do not rewrite the answer.",
        "tools": [],
    },
]
USER = {"messages": [{"role": "user", "content": "What is the GeM purchase rule for laptops?"}]}


def measure(label: str, build) -> dict[str, Any]:
    CAPTURED.clear()
    try:
        agent = build()
        agent.invoke(USER, config={"recursion_limit": 10})
    except Exception as err:  # noqa: BLE001 - a spike records failures and moves on
        return {"label": label, "ok": False, "error": f"{type(err).__name__}: {err}"}
    first = CAPTURED[0]
    tok = get_tokenizer(get_settings().tokenizer_id)
    msgs, tools = first["messages"], first["tools"]
    system = "\n".join(m["content"] for m in msgs if m["role"] == "system")
    return {
        "label": label,
        "ok": True,
        "tool_names": [t["function"]["name"] for t in tools],
        "system_prompt_tokens": count_message_tokens(tok, [{"role": "system", "content": system}]),
        "tool_schema_tokens": count_message_tokens(tok, [], tools) - 3,
        "first_call_prompt_tokens": count_message_tokens(tok, msgs, tools),
        "system_prompt_chars": len(system),
    }


def build_default():
    from deepagents import create_deep_agent

    return create_deep_agent(
        model=CaptureModel(), tools=TOOLS, system_prompt=SHORT_PLANNER, subagents=SUBAGENTS
    )


def build_trimmed():
    from deepagents import SubAgentMiddleware
    from deepagents.backends import StateBackend
    from langchain.agents import create_agent
    from langchain.agents.middleware import TodoListMiddleware

    model = CaptureModel()
    subagents = [{**s, "model": model} for s in SUBAGENTS]
    return create_agent(
        model,
        system_prompt=SHORT_PLANNER,
        tools=[],
        middleware=[
            TodoListMiddleware(),
            SubAgentMiddleware(backend=StateBackend(), subagents=subagents),
        ],
    )


SHORT_TODO_PROMPT = (
    "Plan with write_todos (max 4 items). Mark each done. Answer after the last one."
)
SHORT_TODO_TOOL = (
    "Create or update the todo list. Each item: content, status (pending|in_progress|completed)."
)
SHORT_TASK_TOOL = "Delegate one todo to a subagent. Available agents:\n{available_agents}"


def build_trimmed_short():
    from deepagents import SubAgentMiddleware
    from deepagents.backends import StateBackend
    from langchain.agents import create_agent
    from langchain.agents.middleware import TodoListMiddleware

    model = CaptureModel()
    subagents = [{**s, "model": model} for s in SUBAGENTS]
    return create_agent(
        model,
        system_prompt=SHORT_PLANNER,
        tools=[],
        middleware=[
            TodoListMiddleware(system_prompt=SHORT_TODO_PROMPT, tool_description=SHORT_TODO_TOOL),
            SubAgentMiddleware(
                backend=StateBackend(),
                subagents=subagents,
                system_prompt="",
                task_description=SHORT_TASK_TOOL,
            ),
        ],
    )


def main() -> int:
    results = {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "window_tokens": get_settings().context_window_tokens,
        "configs": [measure("A_default_deep_agent", build_default)],
    }
    results["configs"].append(measure("B_trimmed_todo_plus_subagents", build_trimmed))
    results["configs"].append(measure("C_trimmed_short_descriptions", build_trimmed_short))
    for c in results["configs"]:
        if c["ok"]:
            print(
                f"{c['label']:34s} system={c['system_prompt_tokens']:>5}  "
                f"tools={c['tool_schema_tokens']:>5}  first_call={c['first_call_prompt_tokens']:>5}"
                f"  tools={c['tool_names']}"
            )
        else:
            print(f"{c['label']:34s} FAILED {c['error']}")
    out = PROJECT_ROOT / "docs" / "results" / "siliconflow" / "phase0-deepagents-prompt-size.json"
    out.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
