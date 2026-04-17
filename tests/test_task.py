"""Tests for ``src.task`` — tool determinism, safety, and the dispatcher."""

from __future__ import annotations

import pytest

from src.task import (
    ToolError,
    dispatch,
    query_sales_data,
    summarize_trend,
)


def test_query_is_deterministic():
    sql = (
        "SELECT department, revenue_k_usd FROM sales "
        "WHERE quarter='Q1' AND year=2024 ORDER BY revenue_k_usd DESC"
    )
    first = query_sales_data(sql)
    second = query_sales_data(sql)
    assert first == second
    assert first[0]["department"] == "Sales"


def test_query_rejects_write_statements():
    with pytest.raises(ToolError):
        query_sales_data("DELETE FROM sales")


def test_query_rejects_empty_string():
    with pytest.raises(ToolError):
        query_sales_data("")


def test_summarize_trend_mentions_direction_and_change():
    data_a = [{"department": "Sales", "revenue_k_usd": 2680.0, "quarter": "Q1"}]
    data_b = [{"department": "Sales", "revenue_k_usd": 2410.0, "quarter": "Q4"}]
    summary = summarize_trend(data_a, data_b)
    assert "Revenue" in summary
    assert "increased" in summary
    assert "change" in summary


def test_summarize_trend_handles_flat_case():
    rows = [{"department": "X", "revenue_k_usd": 100.0}]
    out = summarize_trend(rows, rows)
    assert "flat" in out
    assert "+0.0%" in out


def test_summarize_trend_rejects_non_list():
    with pytest.raises(ToolError):
        summarize_trend("a", "b")  # type: ignore[arg-type]


def test_dispatch_returns_record_on_success():
    rec = dispatch("query_sales_data", {"sql": "SELECT * FROM sales LIMIT 1"})
    assert rec.ok
    assert rec.name == "query_sales_data"
    assert rec.result_preview


def test_dispatch_reports_unknown_tool():
    rec = dispatch("does_not_exist", {})
    assert not rec.ok
    assert rec.error and "unknown tool" in rec.error


def test_dispatch_reports_bad_arguments():
    rec = dispatch("query_sales_data", {"not_sql": "x"})
    assert not rec.ok
    assert rec.error


def test_fingerprint_is_stable_across_equal_calls():
    a = dispatch("query_sales_data", {"sql": "SELECT * FROM sales WHERE year=2024"})
    b = dispatch("query_sales_data", {"sql": "SELECT * FROM sales WHERE year=2024"})
    assert a.fingerprint() == b.fingerprint()
