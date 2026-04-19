"""A minimal, deterministic agent orchestrator modeled on ``stage-pilot``.

The intent of this runner is to show what a *production-oriented* tool-calling
loop looks like with no framework dependencies: a bounded retry budget, a
single source of truth for tool schemas, strict argument validation, and a
fingerprintable trace that makes determinism a first-class property.

The algorithm is deliberately small (~200 LOC) so operators can audit every
branch. It is not a reimplementation of LangGraph or CrewAI; it is a
counterweight that shows how much of their complexity is optional.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from ..fixtures import Prompt
from ..metrics import PromptObservation
from ..task import ALL_TOOL_SCHEMAS, ToolCallRecord, dispatch
from .base import BaseRunner

log = logging.getLogger(__name__)


SYSTEM_PROMPT = (
    "You are an analytics agent. You have two tools: query_sales_data(sql) "
    "for fetching rows and summarize_trend(data_a, data_b) for comparing two "
    "row sets. Call query_sales_data first, then summarize_trend, then return "
    "the summary verbatim as your final answer. Respond with tool calls in "
    "OpenAI function-call format; do not wrap arguments in markdown fences."
)


@dataclass
class LoopState:
    """Scratch state passed through the loop; kept minimal for debuggability."""

    messages: List[Dict[str, Any]]
    tool_calls: List[ToolCallRecord]
    retry_count: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    finished: bool = False
    final_answer: str = ""


class StagePilotStyleRunner(BaseRunner):
    """Tool-calling loop that mirrors the stage-pilot ``parser`` runtime.

    Behaviour summary:
      * Build an initial conversation with the system prompt + user message.
      * Repeatedly ask the LLM for the next step.
      * If the LLM emits one or more tool calls, validate and execute them,
        appending a ``tool`` message per call.
      * On malformed calls (bad JSON, unknown tool, schema mismatch) retry up
        to ``config.retry.max_retries`` with exponential backoff.
      * Terminate on the first assistant turn that produces text content, or
        on budget exhaustion.
    """

    name = "stage-pilot-style"

    # Keeps each loop bounded even if the LLM loops forever.
    MAX_STEPS = 8

    def run_prompt(self, prompt: Prompt) -> PromptObservation:
        obs = self._empty_observation(prompt)
        start = time.perf_counter()

        state = LoopState(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt.user_message},
            ],
            tool_calls=[],
        )

        for _step in range(self.MAX_STEPS):
            completion = self._call_llm(prompt, state)
            state.tokens_in += completion.tokens_in
            state.tokens_out += completion.tokens_out

            if completion.tool_calls:
                ok = self._execute_tool_calls(state, completion.tool_calls)
                if not ok and not self._can_retry(state):
                    state.final_answer = ""
                    break
                continue

            if completion.content:
                state.messages.append({"role": "assistant", "content": completion.content})
                state.final_answer = completion.content
                state.finished = True
                break
        else:  # pragma: no cover - exhaustion guard
            log.warning("agent loop exhausted steps for %s", prompt.prompt_id)

        obs.final_answer = state.final_answer
        obs.tool_calls = state.tool_calls
        obs.tokens_in = state.tokens_in
        obs.tokens_out = state.tokens_out
        obs.retry_count = state.retry_count
        obs.latency_ms = (time.perf_counter() - start) * 1000.0
        if not state.finished and not obs.exception:
            obs.exception = "agent loop did not terminate with a final answer"
        return obs

    # ------------------------------------------------------------------
    # Loop internals
    # ------------------------------------------------------------------
    def _call_llm(self, prompt: Prompt, state: LoopState):
        """Delegate to the configured LLM (real or mock)."""
        return self.llm.complete(
            prompt_id=prompt.prompt_id,
            messages=state.messages,
            tools=ALL_TOOL_SCHEMAS,
        )

    def _execute_tool_calls(self, state: LoopState, raw_calls: List[Dict[str, Any]]) -> bool:
        """Validate, dispatch, and append results. Returns False on retry."""
        assistant_msg: Dict[str, Any] = {
            "role": "assistant",
            "content": "",
            "tool_calls": raw_calls,
        }
        state.messages.append(assistant_msg)

        all_ok = True
        for raw in raw_calls:
            name, arguments, err = self._parse_call(raw)
            if err:
                record = ToolCallRecord(
                    name=name or "unknown",
                    arguments={},
                    ok=False,
                    result_preview="",
                    error=err,
                )
                state.tool_calls.append(record)
                all_ok = False
                state.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": raw.get("id", "?"),
                        "name": name or "unknown",
                        "content": json.dumps({"error": err}),
                    }
                )
                continue

            record = dispatch(name, arguments)
            state.tool_calls.append(record)
            if not record.ok:
                all_ok = False
                payload = {"error": record.error or "tool failed"}
            else:
                payload = _payload_from_preview(record.result_preview, arguments, name)

            state.messages.append(
                {
                    "role": "tool",
                    "tool_call_id": raw.get("id", "?"),
                    "name": name,
                    "content": json.dumps(payload, default=str),
                }
            )

        if not all_ok:
            state.retry_count += 1
            self._backoff(state.retry_count)
        return all_ok

    def _parse_call(
        self, raw: Dict[str, Any]
    ) -> Tuple[Optional[str], Dict[str, Any], Optional[str]]:
        fn = raw.get("function") or {}
        name = fn.get("name")
        if not isinstance(name, str):
            return None, {}, "missing function.name"
        args_raw = fn.get("arguments")
        if isinstance(args_raw, dict):
            return name, args_raw, None
        if not isinstance(args_raw, str):
            return name, {}, "arguments must be a JSON string or object"
        cleaned = _strip_markdown_fences(args_raw)
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            return name, {}, f"invalid JSON arguments: {exc.msg}"
        if not isinstance(parsed, dict):
            return name, {}, "arguments must parse to a JSON object"
        return name, parsed, None

    def _can_retry(self, state: LoopState) -> bool:
        return state.retry_count <= self.config.retry.max_retries

    def _backoff(self, attempt: int) -> None:
        policy = self.config.retry
        delay = min(
            policy.max_backoff_s,
            policy.initial_backoff_s * (policy.backoff_multiplier ** max(0, attempt - 1)),
        )
        # Sleep is skipped when the mock LLM is in use so tests stay fast.
        if not self.config.use_mock_llm and delay > 0:
            time.sleep(delay)


# ----------------------------------------------------------------------
# Small utilities shared only within this module
# ----------------------------------------------------------------------
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def _strip_markdown_fences(text: str) -> str:
    """Remove triple-backtick wrappers some LLMs emit around JSON payloads."""
    text = text.strip()
    text = _FENCE_RE.sub("", text)
    return text.strip()


def _payload_from_preview(preview: str, arguments: Dict[str, Any], tool_name: str) -> Any:
    """Rehydrate a tool's JSON preview for the next conversation turn.

    Preserves the original tool return shape when possible so the LLM can
    feed it straight into the next call without additional transforms.
    """
    if not preview:
        return {"ok": True, "tool": tool_name, "arguments": arguments}
    try:
        return json.loads(preview)
    except json.JSONDecodeError:
        return preview
