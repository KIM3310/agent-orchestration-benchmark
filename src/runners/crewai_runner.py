"""CrewAI adapter.

CrewAI models agents as role-playing crew members that delegate work to each
other. For a two-tool analytics task the crew is small: an ``analyst`` who
writes SQL and a ``reporter`` who turns rows into narrative. In mock mode the
runner simulates the hand-off explicitly; in live mode the same structure is
expressed with the real ``crewai`` classes.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List

from ..fixtures import Prompt
from ..metrics import PromptObservation
from ..task import ALL_TOOL_SCHEMAS, ToolCallRecord, dispatch
from .base import BaseRunner


class CrewAIRunner(BaseRunner):
    """Role-based orchestrator modeled after a two-member CrewAI crew."""

    name = "crewai"

    ROLES: List[str] = ["analyst", "reporter"]

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

        # Analyst step: produce the SQL call.
        analyst = self.llm.complete(
            prompt_id=prompt.prompt_id, messages=messages, tools=ALL_TOOL_SCHEMAS
        )
        tokens_in += analyst.tokens_in
        tokens_out += analyst.tokens_out
        query_result = None
        for raw in analyst.tool_calls:
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
            if record.ok:
                try:
                    query_result = json.loads(record.result_preview)
                except json.JSONDecodeError:
                    query_result = []
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": raw.get("id", "?"),
                        "name": name,
                        "content": record.result_preview,
                    }
                )

        # Reporter step: consume the analyst's result and summarize.
        reporter = self.llm.complete(
            prompt_id=prompt.prompt_id, messages=messages, tools=ALL_TOOL_SCHEMAS
        )
        tokens_in += reporter.tokens_in
        tokens_out += reporter.tokens_out
        for raw in reporter.tool_calls:
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
            if record.ok:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": raw.get("id", "?"),
                        "name": name,
                        "content": record.result_preview,
                    }
                )

        final = self.llm.complete(
            prompt_id=prompt.prompt_id, messages=messages, tools=ALL_TOOL_SCHEMAS
        )
        tokens_in += final.tokens_in
        tokens_out += final.tokens_out

        obs.final_answer = final.content
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
            from crewai import Agent, Crew, Task  # type: ignore
        except ImportError as exc:
            obs = self._empty_observation(prompt)
            obs.exception = f"crewai not installed: {exc}"
            return obs

        obs = self._empty_observation(prompt)
        start = time.perf_counter()
        try:
            analyst = Agent(
                role="analyst", goal="write SQL", backstory="quant analyst"
            )
            reporter = Agent(
                role="reporter", goal="summarize", backstory="BI writer"
            )
            crew = Crew(
                agents=[analyst, reporter],
                tasks=[
                    Task(description=prompt.user_message, agent=analyst),
                    Task(description="summarize the rows", agent=reporter),
                ],
            )
            obs.final_answer = str(crew.kickoff())
        except Exception as exc:  # noqa: BLE001
            obs.exception = repr(exc)
        obs.latency_ms = (time.perf_counter() - start) * 1000.0
        return obs

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You are an analytics crew. The analyst runs query_sales_data to "
            "fetch rows. The reporter runs summarize_trend and returns the "
            "one-paragraph summary as the final answer."
        )
