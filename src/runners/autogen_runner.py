"""AutoGen adapter.

AutoGen centres on a conversational loop between a user-proxy and an
assistant that can invoke tools. The mock implementation keeps the same
two-party shape: a proxy forwards the user prompt, the assistant calls the
tools, and the proxy forwards tool results back until the assistant emits a
final message.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List

from ..fixtures import Prompt
from ..metrics import PromptObservation
from ..task import ALL_TOOL_SCHEMAS, ToolCallRecord, dispatch
from .base import BaseRunner


class AutoGenRunner(BaseRunner):
    """Conversational agent pair mirroring a minimal AutoGen setup."""

    name = "autogen"

    MAX_TURNS = 8

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

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self._system_prompt()},
            {"role": "user", "content": prompt.user_message},
        ]
        tool_calls: List[ToolCallRecord] = []
        tokens_in = 0
        tokens_out = 0
        retries = 0

        final_answer = ""
        for _ in range(self.MAX_TURNS):
            completion = self.llm.complete(
                prompt_id=prompt.prompt_id, messages=messages, tools=ALL_TOOL_SCHEMAS
            )
            tokens_in += completion.tokens_in
            tokens_out += completion.tokens_out

            if not completion.tool_calls:
                final_answer = completion.content
                messages.append({"role": "assistant", "content": completion.content})
                break

            messages.append(
                {"role": "assistant", "content": "", "tool_calls": completion.tool_calls}
            )
            for raw in completion.tool_calls:
                name = raw["function"]["name"]
                try:
                    arguments = json.loads(raw["function"]["arguments"])
                except json.JSONDecodeError:
                    retries += 1
                    tool_calls.append(
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
                tool_calls.append(record)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": raw.get("id", "?"),
                        "name": name,
                        "content": record.result_preview or json.dumps({"error": record.error}),
                    }
                )

        obs.final_answer = final_answer
        obs.tool_calls = tool_calls
        obs.tokens_in = tokens_in
        obs.tokens_out = tokens_out
        obs.retry_count = retries
        obs.latency_ms = (time.perf_counter() - start) * 1000.0
        return obs

    # ------------------------------------------------------------------
    # Live mode
    # ------------------------------------------------------------------
    def _run_live(self, prompt: Prompt) -> PromptObservation:  # pragma: no cover
        try:
            from autogen import AssistantAgent, UserProxyAgent  # type: ignore
        except ImportError as exc:
            obs = self._empty_observation(prompt)
            obs.exception = f"autogen not installed: {exc}"
            return obs

        obs = self._empty_observation(prompt)
        start = time.perf_counter()
        try:
            assistant = AssistantAgent("assistant", llm_config={})
            user = UserProxyAgent("user_proxy", code_execution_config=False)
            user.initiate_chat(assistant, message=prompt.user_message)
            obs.final_answer = str(user.last_message().get("content", ""))
        except Exception as exc:  # noqa: BLE001
            obs.exception = repr(exc)
        obs.latency_ms = (time.perf_counter() - start) * 1000.0
        return obs

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You are an AutoGen assistant. Use query_sales_data, then "
            "summarize_trend, then return the summary. The user proxy will "
            "forward tool results back as tool messages."
        )
