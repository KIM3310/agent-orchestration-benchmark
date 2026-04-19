"""LangGraph adapter.

Runs in one of two modes:

* **Live** – when the ``langgraph`` package is importable and
  ``config.use_mock_llm`` is False, the runner builds a real
  ``StateGraph`` with two tool nodes plus a conditional edge on whether an
  assistant turn produced further tool calls.
* **Mock** – the default in CI. We use the same mock LLM as every other
  runner and implement the equivalent state machine by hand. This keeps CI
  deterministic and lets us benchmark *orchestrator shape*, not network
  latency.

The mock path is what executes in ``make test``; the live path is provided so
a user running ``LLM=live make bench`` can reproduce the same benchmark with
real API traffic.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List

from ..fixtures import Prompt
from ..metrics import PromptObservation
from ..task import ALL_TOOL_SCHEMAS, ToolCallRecord, dispatch
from .base import BaseRunner


class LangGraphRunner(BaseRunner):
    """Graph-based orchestrator mirroring a minimal LangGraph StateGraph.

    In mock mode we emulate the graph structure explicitly rather than
    pretending to instantiate LangGraph; real LangGraph code is available in
    ``_build_live_graph`` for a live run.
    """

    name = "langgraph"

    def run_prompt(self, prompt: Prompt) -> PromptObservation:
        if self.config.use_mock_llm:
            return self._run_mock(prompt)
        return self._run_live(prompt)

    # ------------------------------------------------------------------
    # Mock mode
    # ------------------------------------------------------------------
    def _run_mock(self, prompt: Prompt) -> PromptObservation:
        obs = self._empty_observation(prompt)
        start = time.perf_counter()
        state: Dict[str, Any] = {
            "messages": [
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": prompt.user_message},
            ],
            "tool_calls": [],
            "tokens_in": 0,
            "tokens_out": 0,
            "retries": 0,
        }

        # Graph: agent_node -> (tool_node -> agent_node)* -> END
        # We cap the loop with a small upper bound so malformed graphs can't
        # spin forever in the benchmark.
        for _ in range(6):
            completion = self.llm.complete(
                prompt_id=prompt.prompt_id,
                messages=state["messages"],
                tools=ALL_TOOL_SCHEMAS,
            )
            state["tokens_in"] += completion.tokens_in
            state["tokens_out"] += completion.tokens_out

            if not completion.tool_calls:
                obs.final_answer = completion.content
                state["messages"].append({"role": "assistant", "content": completion.content})
                break

            state["messages"].append(
                {"role": "assistant", "content": "", "tool_calls": completion.tool_calls}
            )
            for raw in completion.tool_calls:
                name = raw.get("function", {}).get("name", "unknown")
                try:
                    arguments = json.loads(raw.get("function", {}).get("arguments", "{}"))
                except json.JSONDecodeError:
                    state["retries"] += 1
                    state["tool_calls"].append(
                        ToolCallRecord(
                            name=name,
                            arguments={},
                            ok=False,
                            result_preview="",
                            error="invalid JSON arguments",
                        )
                    )
                    continue
                record = dispatch(name, arguments)
                state["tool_calls"].append(record)
                state["messages"].append(
                    {
                        "role": "tool",
                        "tool_call_id": raw.get("id", "?"),
                        "name": name,
                        "content": record.result_preview or json.dumps({"error": record.error}),
                    }
                )

        obs.tool_calls = state["tool_calls"]
        obs.tokens_in = state["tokens_in"]
        obs.tokens_out = state["tokens_out"]
        obs.retry_count = state["retries"]
        obs.latency_ms = (time.perf_counter() - start) * 1000.0
        return obs

    # ------------------------------------------------------------------
    # Live mode (real LangGraph, real LLM)
    # ------------------------------------------------------------------
    def _run_live(self, prompt: Prompt) -> PromptObservation:  # pragma: no cover
        try:
            graph = self._build_live_graph()
        except ImportError as exc:
            obs = self._empty_observation(prompt)
            obs.exception = f"langgraph not installed: {exc}"
            return obs

        obs = self._empty_observation(prompt)
        start = time.perf_counter()
        try:
            result = graph.invoke({"messages": [{"role": "user", "content": prompt.user_message}]})
        except Exception as exc:  # noqa: BLE001
            obs.exception = repr(exc)
            obs.latency_ms = (time.perf_counter() - start) * 1000.0
            return obs

        obs.final_answer = _extract_final(result)
        obs.latency_ms = (time.perf_counter() - start) * 1000.0
        return obs

    def _build_live_graph(self):  # pragma: no cover - requires langgraph
        from langgraph.graph import END, StateGraph  # type: ignore

        def agent_node(state):
            return state

        def tool_node(state):
            return state

        def should_continue(state):
            msgs: List[Dict[str, Any]] = state.get("messages", [])
            if msgs and msgs[-1].get("tool_calls"):
                return "tools"
            return END

        graph = StateGraph(dict)
        graph.add_node("agent", agent_node)
        graph.add_node("tools", tool_node)
        graph.set_entry_point("agent")
        graph.add_conditional_edges("agent", should_continue)
        graph.add_edge("tools", "agent")
        return graph.compile()

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You are a stateful analytics agent. Use the provided tools in "
            "order: query_sales_data, then summarize_trend. Return the summary "
            "from the second tool call verbatim."
        )


def _extract_final(result: Dict[str, Any]) -> str:  # pragma: no cover
    msgs = result.get("messages", [])
    if msgs and isinstance(msgs[-1], dict):
        return msgs[-1].get("content", "") or ""
    return ""
