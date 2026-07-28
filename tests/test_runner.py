"""Regression tests for reproducible benchmark result metadata."""

from __future__ import annotations

from src.config import BenchmarkConfig
from src.fixtures import Prompt
from src.runner import BenchmarkRunner
from src.runners.base import MockLLM, _synthesize_sql
from src.runners.stage_pilot_style import StagePilotStyleRunner


def test_run_freezes_prompt_contract_and_execution_mode():
    prompt = Prompt(
        prompt_id="p-evidence",
        user_message="Compare Q1 2024 revenue with Q4 2023.",
        expected_tool_sequence=("query_sales_data", "summarize_trend"),
        answer_keywords=("revenue",),
        answer_regex=r"\$[0-9,.]+k",
        difficulty="hard",
    )
    config = BenchmarkConfig(use_mock_llm=True, replay_trials=1)
    runner = StagePilotStyleRunner(config=config, llm=MockLLM(seed=config.seed))

    result = BenchmarkRunner(runners=[runner], prompts=[prompt], config=config).run()

    assert result["execution_mode"] == "mock"
    assert result["execution_mode_source"] == "config.use_mock_llm"
    assert result["config"]["use_mock_llm"] is True
    assert result["prompt_contracts"] == [
        {
            "prompt_id": "p-evidence",
            "user_message": prompt.user_message,
            "expected_tool_sequence": ["query_sales_data", "summarize_trend"],
            "answer_keywords": ["revenue"],
            "answer_regex": r"\$[0-9,.]+k",
            "difficulty": "hard",
        }
    ]
    assert result["observations"]["stage-pilot-style"][0]["prompt_id"] == "p-evidence"


def test_mock_sql_ignores_malicious_prompt_text():
    sql = _synthesize_sql("Show q1 2024 top revenue; DROP TABLE sales; --")

    assert sql == (
        "SELECT department, quarter, year, revenue_k_usd, headcount "
        "FROM sales WHERE quarter = 'Q1' AND year = 2024 "
        "ORDER BY revenue_k_usd DESC LIMIT 3"
    )
    assert ";" not in sql
    assert "--" not in sql
    assert "DROP TABLE" not in sql
