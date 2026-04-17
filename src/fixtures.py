"""Load and validate the 20-prompt benchmark fixture set."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Sequence

from .config import FIXTURES_DIR


@dataclass(frozen=True)
class Prompt:
    """A single benchmark prompt with its grading contract.

    Attributes:
        prompt_id: Stable identifier, e.g. ``p-001``. Used as a primary key in
            results files so re-runs can diff against historical results.
        user_message: The natural-language request shown to the agent.
        expected_tool_sequence: The exact ordered list of tool names the
            agent should call. Used to compute ``tool_call_success_rate``.
        answer_keywords: Tokens that must appear (case-insensitively) in the
            agent's final answer. Missing any keyword scores 0 for this prompt.
        answer_regex: Optional regex that must match the final answer if
            ``answer_keywords`` alone isn't precise enough.
        difficulty: Coarse bucket used for reporting slices. One of ``easy``,
            ``medium``, ``hard``.
    """

    prompt_id: str
    user_message: str
    expected_tool_sequence: Sequence[str]
    answer_keywords: Sequence[str]
    answer_regex: str
    difficulty: str

    def answer_matches(self, final_answer: str) -> bool:
        """Return True if ``final_answer`` satisfies both keyword and regex
        constraints. Keywords are compared case-insensitively."""
        hay = final_answer.lower()
        if any(kw.lower() not in hay for kw in self.answer_keywords):
            return False
        if self.answer_regex:
            try:
                if re.search(self.answer_regex, final_answer, re.IGNORECASE) is None:
                    return False
            except re.error:
                return False
        return True


DEFAULT_FIXTURE_PATH: Path = FIXTURES_DIR / "benchmark_prompts.jsonl"


def load_prompts(path: Path | str = DEFAULT_FIXTURE_PATH) -> List[Prompt]:
    """Load prompts from a JSONL file; defaults to the bundled fixture."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"prompt fixture not found: {p}")
    prompts: List[Prompt] = []
    for line_no, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON on line {line_no}: {exc}") from exc
        prompts.append(
            Prompt(
                prompt_id=data["prompt_id"],
                user_message=data["user_message"],
                expected_tool_sequence=list(data["expected_tool_sequence"]),
                answer_keywords=list(data["answer_keywords"]),
                answer_regex=data.get("answer_regex", ""),
                difficulty=data.get("difficulty", "medium"),
            )
        )
    _validate(prompts)
    return prompts


def _validate(prompts: List[Prompt]) -> None:
    if not prompts:
        raise ValueError("fixture file contained no prompts")
    ids = [p.prompt_id for p in prompts]
    if len(ids) != len(set(ids)):
        raise ValueError("fixture contains duplicate prompt_id values")
    for p in prompts:
        if not p.user_message:
            raise ValueError(f"{p.prompt_id}: user_message cannot be empty")
        if not p.expected_tool_sequence:
            raise ValueError(f"{p.prompt_id}: expected_tool_sequence cannot be empty")


def iter_prompts(path: Path | str = DEFAULT_FIXTURE_PATH) -> Iterator[Prompt]:
    """Generator-style access for streaming over the fixture file."""
    yield from load_prompts(path)
