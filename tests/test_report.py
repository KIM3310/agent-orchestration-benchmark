"""Tests for report rendering."""

from __future__ import annotations

import copy
import json

from src.report import framework_leaderboard, render_html, render_markdown


def _sample_result():
    return {
        "generated_at": "2026-04-16T00:00:00+00:00",
        "model": "gpt-4o-mini",
        "n_prompts": 20,
        "execution_mode": "mock",
        "execution_mode_source": "config.use_mock_llm",
        "config": {
            "seed": 1,
            "replay_trials": 3,
            "temperature": 0.0,
            "max_tokens": 512,
            "use_mock_llm": True,
        },
        "prompt_contracts": [
            {
                "prompt_id": "p-001",
                "user_message": "Compare <script>alert('x')</script> revenue.",
                "expected_tool_sequence": ["query_sales_data", "summarize_trend"],
                "answer_keywords": ["revenue", "change"],
                "answer_regex": r"\$[0-9,.]+k",
                "difficulty": "easy",
            }
        ],
        "summaries": [
            {
                "framework": "stage-pilot-style",
                "n_prompts": 20,
                "tool_call_success_rate": 0.95,
                "final_answer_quality": 0.90,
                "latency_p50_ms": 10.0,
                "latency_p95_ms": 40.0,
                "latency_p99_ms": 60.0,
                "tokens_in": 1000,
                "tokens_out": 500,
                "total_cost_usd": 0.001,
                "retry_count": 1,
                "exception_rate": 0.0,
                "deterministic_replay_rate": 1.0,
            },
            {
                "framework": "langgraph",
                "n_prompts": 20,
                "tool_call_success_rate": 0.90,
                "final_answer_quality": 0.85,
                "latency_p50_ms": 20.0,
                "latency_p95_ms": 80.0,
                "latency_p99_ms": 110.0,
                "tokens_in": 1100,
                "tokens_out": 600,
                "total_cost_usd": 0.002,
                "retry_count": 3,
                "exception_rate": 0.05,
                "deterministic_replay_rate": 0.95,
            },
        ],
        "observations": {
            "stage-pilot-style": [
                {
                    "prompt_id": "p-001",
                    "framework": "stage-pilot-style",
                    "final_answer": "Revenue increased...",
                    "tool_calls": [
                        {
                            "name": "query_sales_data",
                            "arguments": {"sql": "SELECT * FROM sales"},
                            "ok": True,
                            "result_preview": '[{"department": "Sales"}]',
                            "error": None,
                        },
                        {
                            "name": "summarize_trend",
                            "arguments": {},
                            "ok": True,
                            "result_preview": "",
                            "error": None,
                        },
                    ],
                    "tokens_in": 50,
                    "tokens_out": 25,
                    "latency_ms": 10.0,
                    "retry_count": 0,
                    "exception": "",
                    "replay_fingerprints": ["a", "a", "a"],
                }
            ]
        },
    }


def test_markdown_contains_header_and_rows():
    md = render_markdown(_sample_result())
    assert "# Agent Orchestration Benchmark Results" in md
    assert "stage-pilot-style" in md
    assert "langgraph" in md
    assert "| Framework |" in md


def test_html_contains_table_structure():
    html = render_html(_sample_result())
    assert "<html" in html
    assert "<table" in html
    assert "stage-pilot-style" in html
    assert "MOCK / SYNTHETIC" in html
    assert "Mode basis:" in html
    assert "config.use_mock_llm" in html
    assert "Expected" in html
    assert "Observed attempted calls" in html
    assert "query_sales_data" in html
    assert "summarize_trend" in html
    assert "EXACT MATCH" in html
    assert "SELECT * FROM sales" in html
    assert "Revenue increased..." in html


def test_html_exact_match_counts_failed_extra_attempts_as_mismatch():
    result = _sample_result()
    observation = result["observations"]["stage-pilot-style"][0]
    observation["tool_calls"].insert(
        1,
        {
            "name": "send_email",
            "arguments": {"to": "sales@example.com"},
            "ok": False,
            "result_preview": "",
            "error": "unknown tool",
        },
    )

    html = render_html(result)
    assert "Observed attempted calls" in html
    assert "send_email" in html
    assert "unknown tool" in html
    assert "MISMATCH" in html
    assert "EXACT MATCH" not in html


def test_html_preserves_prompt_contract_and_escapes_untrusted_evidence():
    html = render_html(_sample_result())
    assert "Compare &lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt; revenue." in html
    assert "<script>alert('x')</script>" not in html
    assert r"\$[0-9,.]+k" in html


def test_html_labels_live_configured_runs_without_overclaiming_provider_traffic():
    result = copy.deepcopy(_sample_result())
    result["execution_mode"] = "live"
    result["config"]["use_mock_llm"] = False
    html = render_html(result)
    assert "LIVE / CONFIGURED" in html
    assert "This label alone does not prove provider traffic" in html


def test_json_roundtrip_is_stable():
    result = _sample_result()
    blob = json.dumps(result)
    back = json.loads(blob)
    assert back["n_prompts"] == result["n_prompts"]


def test_leaderboard_ranks_by_combined_score():
    order = list(framework_leaderboard(_sample_result()))
    assert order[0] == "stage-pilot-style"
    assert set(order) == {"stage-pilot-style", "langgraph"}
