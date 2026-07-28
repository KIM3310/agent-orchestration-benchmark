"""Runner interface and a deterministic Mock LLM shared across adapters.

Every framework-specific runner subclasses :class:`BaseRunner` and implements
``run_prompt``. The :class:`MockLLM` below gives all runners a reproducible way
to behave as if an LLM were present during CI without spending any API budget.
The mock responds based on lexical cues in the prompt, which is plenty to
exercise tool-selection logic without pretending to be clever.
"""

from __future__ import annotations

import json
import random
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..config import BenchmarkConfig
from ..fixtures import Prompt
from ..metrics import PromptObservation
from ..task import ToolCallRecord


@dataclass
class MockCompletion:
    """Shape returned by :meth:`MockLLM.complete`, mirroring the fields we use
    from the OpenAI SDK response object."""

    content: str
    tool_calls: List[Dict[str, Any]]
    tokens_in: int
    tokens_out: int


@dataclass
class MockLLM:
    """Deterministic LLM stand-in for CI and local development.

    The mock runs a tiny state machine: first call emits a ``query_sales_data``
    tool call with SQL derived from the prompt text, second call emits a
    ``summarize_trend`` call wrapping the result from the first, third call
    produces the final natural-language answer. The exact same prompt always
    produces the exact same sequence, which is the whole point.

    State is keyed on ``prompt_id`` so concurrent prompts don't interfere.
    Call :meth:`reset_prompt` at the start of each replay trial to get the
    same sequence again; the benchmark runner does this for determinism
    measurements.
    """

    seed: int = 2026_04_16
    call_counter: Dict[str, int] = field(default_factory=dict)

    def reset_prompt(self, prompt_id: str) -> None:
        """Clear internal state for a single prompt so the next call to
        :meth:`complete` restarts the mock's state machine from zero."""
        self.call_counter.pop(prompt_id, None)

    def complete(
        self, *, prompt_id: str, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]
    ) -> MockCompletion:
        state = self.call_counter.get(prompt_id, 0)
        self.call_counter[prompt_id] = state + 1

        user_text = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_text = msg.get("content", "") or ""
                break
        if state == 0:
            sql = _synthesize_sql(user_text)
            call = {
                "id": f"call-{prompt_id}-0",
                "type": "function",
                "function": {
                    "name": "query_sales_data",
                    "arguments": json.dumps({"sql": sql}),
                },
            }
            return MockCompletion(
                content="",
                tool_calls=[call],
                tokens_in=_approx_tokens(messages),
                tokens_out=32,
            )

        if state == 1:
            prev_result = _last_tool_result(messages)
            data_a, data_b = _split_for_trend(prev_result, user_text)
            call = {
                "id": f"call-{prompt_id}-1",
                "type": "function",
                "function": {
                    "name": "summarize_trend",
                    "arguments": json.dumps({"data_a": data_a, "data_b": data_b}),
                },
            }
            return MockCompletion(
                content="",
                tool_calls=[call],
                tokens_in=_approx_tokens(messages),
                tokens_out=48,
            )

        # state >= 2: wrap the last tool result as the final answer.
        summary = _last_tool_result(messages)
        if not isinstance(summary, str):
            summary = json.dumps(summary)
        return MockCompletion(
            content=summary,
            tool_calls=[],
            tokens_in=_approx_tokens(messages),
            tokens_out=max(16, len(summary) // 4),
        )


# ---------------------------------------------------------------------------
# Helpers used by MockLLM to produce deterministic tool arguments
# ---------------------------------------------------------------------------
def _approx_tokens(messages: List[Dict[str, Any]]) -> int:
    """Rough ~4 chars per token estimate; stable enough for cost metrics."""
    joined = json.dumps(messages, default=str)
    return max(1, len(joined) // 4)


def _last_tool_result(messages: List[Dict[str, Any]]) -> Any:
    for msg in reversed(messages):
        if msg.get("role") == "tool":
            content = msg.get("content")
            if isinstance(content, str):
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    return content
            return content
    return []


def _synthesize_sql(user_text: str) -> str:
    """Produce a SQL query for the mocked LLM using cues in the user prompt.

    The heuristic is intentionally dumb: it picks the narrowest WHERE clause it
    can infer from keywords. It exists only so benchmarks touching the mock
    exercise non-trivial arguments.
    """
    lowered = user_text.lower()
    quarter = _detect_quarter(lowered)
    year = _detect_year(lowered)

    where_parts: List[str] = []
    if quarter:
        where_parts.append(f"quarter = '{quarter}'")
    if year:
        where_parts.append(f"year = {year}")

    where = f" WHERE {' AND '.join(where_parts)}" if where_parts else ""
    limit = 10 if "top" not in lowered else 3
    # Bandit B608 rationale: mock SQL uses fixed fragments plus regex quarter/internal int year/limit.
    return (
        "SELECT department, quarter, year, revenue_k_usd, headcount "
        f"FROM sales{where} ORDER BY revenue_k_usd DESC LIMIT {limit}"  # nosec B608
    )


_QUARTER_RE = re.compile(r"\bq([1-4])\b", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(20\d{2})\b")


def _detect_quarter(text: str) -> Optional[str]:
    m = _QUARTER_RE.search(text)
    return f"Q{m.group(1)}" if m else None


def _detect_year(text: str) -> Optional[int]:
    m = _YEAR_RE.search(text)
    return int(m.group(1)) if m else None


def _split_for_trend(prev_result: Any, user_text: str) -> tuple[list, list]:
    """Turn the prior query result into two halves suitable for summarize_trend.

    When the prompt references two comparison quarters we split rows on
    ``quarter``; otherwise we split the list in half so the tool still receives
    two non-empty operands.
    """
    rows: List[Dict[str, Any]] = prev_result if isinstance(prev_result, list) else []
    quarters = sorted({r.get("quarter") for r in rows if r.get("quarter")})
    if len(quarters) >= 2:
        a = [r for r in rows if r.get("quarter") == quarters[-1]]
        b = [r for r in rows if r.get("quarter") == quarters[0]]
        return a, b
    mid = max(1, len(rows) // 2)
    return rows[:mid], rows[mid:] or rows[:mid]


# ---------------------------------------------------------------------------
# Runner protocol
# ---------------------------------------------------------------------------
class BaseRunner(ABC):
    """Adapter interface every framework-specific runner must implement."""

    name: str = "base"

    def __init__(
        self,
        config: Optional[BenchmarkConfig] = None,
        llm: Optional[MockLLM] = None,
    ) -> None:
        self.config = config or BenchmarkConfig()
        self.llm = llm or MockLLM(seed=self.config.seed)
        self._rng = random.Random(self.config.seed)  # nosec B311

    # -- public API --------------------------------------------------------
    @abstractmethod
    def run_prompt(self, prompt: Prompt) -> PromptObservation:
        """Execute a single prompt and return a populated observation."""

    def reset_for_prompt(self, prompt: Prompt) -> None:
        """Reset per-prompt state (default: reset MockLLM state if present).

        Overridden by adapters that hold additional state across prompts.
        Called by :class:`BenchmarkRunner` before each trial.
        """
        if isinstance(self.llm, MockLLM):
            self.llm.reset_prompt(prompt.prompt_id)

    # -- helpers usable by subclasses -------------------------------------
    def _empty_observation(self, prompt: Prompt) -> PromptObservation:
        return PromptObservation(
            prompt_id=prompt.prompt_id,
            framework=self.name,
            final_answer="",
        )

    def _record_call(
        self, name: str, arguments: Dict[str, Any], result: Any, ok: bool, error: str = ""
    ) -> ToolCallRecord:
        preview = ""
        if ok:
            try:
                preview = json.dumps(result, default=str)
            except (TypeError, ValueError):
                preview = str(result)
            if len(preview) > 500:
                preview = preview[:497] + "..."
        return ToolCallRecord(
            name=name,
            arguments=arguments,
            ok=ok,
            result_preview=preview,
            error=error or None,
        )

    def _now_ms(self) -> float:
        return time.perf_counter() * 1000.0
