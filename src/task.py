"""The standardized benchmark task and its two tools.

The agent under test must solve a three-step task:

    1. Receive a natural-language analytics request.
    2. Call ``query_sales_data(sql)`` to fetch rows from a mocked deterministic
       SQLite database.
    3. Call ``summarize_trend(data_a, data_b)`` to produce a comparative
       paragraph describing how ``data_a`` differs from ``data_b``.

Both tools are intentionally deterministic: identical inputs produce identical
outputs. This lets the benchmark report a ``deterministic_replay_rate`` that
reflects the agent's decision-making, not tool noise.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Tool schemas (OpenAI "tools" format; LangGraph/CrewAI/AutoGen adapters
# translate these into their native bindings in the runners package)
# ---------------------------------------------------------------------------
QUERY_TOOL_SCHEMA: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "query_sales_data",
        "description": (
            "Run a SELECT query against the sales warehouse. Supports standard "
            "SQLite SQL. Returns a list of row dictionaries."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "A SELECT statement. Must be read-only.",
                }
            },
            "required": ["sql"],
        },
    },
}

SUMMARIZE_TOOL_SCHEMA: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "summarize_trend",
        "description": (
            "Produce a one-paragraph natural-language summary comparing "
            "``data_a`` against ``data_b``. Both arguments are lists of row "
            "dictionaries returned by ``query_sales_data``."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "data_a": {"type": "array", "items": {"type": "object"}},
                "data_b": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["data_a", "data_b"],
        },
    },
}

ALL_TOOL_SCHEMAS: List[Dict[str, Any]] = [QUERY_TOOL_SCHEMA, SUMMARIZE_TOOL_SCHEMA]


# ---------------------------------------------------------------------------
# Deterministic seed data
# ---------------------------------------------------------------------------
# Department sales, quarterly, USD (in thousands). Numbers are arbitrary but
# stable; any change here must be accompanied by an update to the expected
# answer patterns in ``fixtures/benchmark_prompts.jsonl``.
_SEED_ROWS: List[Tuple[str, str, int, float, int]] = [
    # (department, quarter, year, revenue_k_usd, headcount)
    ("Engineering", "Q4", 2023, 1820.0, 54),
    ("Engineering", "Q1", 2024, 1975.0, 57),
    ("Sales", "Q4", 2023, 2410.0, 38),
    ("Sales", "Q1", 2024, 2680.0, 41),
    ("Marketing", "Q4", 2023, 610.0, 18),
    ("Marketing", "Q1", 2024, 705.0, 20),
    ("Support", "Q4", 2023, 390.0, 22),
    ("Support", "Q1", 2024, 420.0, 24),
    ("Research", "Q4", 2023, 840.0, 16),
    ("Research", "Q1", 2024, 905.0, 17),
    ("Operations", "Q4", 2023, 510.0, 28),
    ("Operations", "Q1", 2024, 540.0, 29),
    ("Finance", "Q4", 2023, 480.0, 12),
    ("Finance", "Q1", 2024, 495.0, 12),
    ("HR", "Q4", 2023, 210.0, 9),
    ("HR", "Q1", 2024, 225.0, 10),
]


def _build_in_memory_db() -> sqlite3.Connection:
    """Construct a fresh in-memory SQLite populated with the seed dataset."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE sales (
            department TEXT NOT NULL,
            quarter TEXT NOT NULL,
            year INTEGER NOT NULL,
            revenue_k_usd REAL NOT NULL,
            headcount INTEGER NOT NULL
        );
        """)
    conn.executemany(
        "INSERT INTO sales VALUES (?, ?, ?, ?, ?)",
        _SEED_ROWS,
    )
    conn.commit()
    return conn


# Module-level singleton so repeated calls don't pay rebuild cost and all tool
# invocations within a process share identical state.
_DB: Optional[sqlite3.Connection] = None


def _db() -> sqlite3.Connection:
    global _DB
    if _DB is None:
        _DB = _build_in_memory_db()
    return _DB


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------
class ToolError(RuntimeError):
    """Raised when a tool call is invalid or violates safety constraints."""


_FORBIDDEN_SQL = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|ATTACH|REPLACE|TRUNCATE)\b",
    re.IGNORECASE,
)


def query_sales_data(sql: str) -> List[Dict[str, Any]]:
    """Run a read-only SQL query against the seed database.

    Args:
        sql: A SELECT statement. Write operations are rejected with
            :class:`ToolError` so the benchmark can count bad tool calls
            without corrupting state.

    Returns:
        A list of row dictionaries. Deterministic for a given ``sql`` string.
    """
    if not isinstance(sql, str) or not sql.strip():
        raise ToolError("sql must be a non-empty string")
    if _FORBIDDEN_SQL.search(sql):
        raise ToolError("only SELECT statements are permitted")
    try:
        cur = _db().execute(sql)
    except sqlite3.Error as exc:  # pragma: no cover - error surface
        raise ToolError(f"sqlite error: {exc}") from exc
    return [dict(row) for row in cur.fetchall()]


def summarize_trend(data_a: List[Dict[str, Any]], data_b: List[Dict[str, Any]]) -> str:
    """Produce a deterministic one-paragraph comparison of two result sets.

    The summary is computed analytically (no LLM call) so that agent quality
    is measured on *tool selection and argument passing* rather than on the
    fluency of a nested model call.
    """
    if not isinstance(data_a, list) or not isinstance(data_b, list):
        raise ToolError("data_a and data_b must both be lists of row dicts")

    total_a = _sum_revenue(data_a)
    total_b = _sum_revenue(data_b)
    delta = total_a - total_b
    pct = (delta / total_b * 100.0) if total_b else 0.0

    leaders_a = _top_departments(data_a, k=3)
    leaders_b = _top_departments(data_b, k=3)

    direction = "increased" if delta > 0 else "decreased" if delta < 0 else "held flat"
    leader_clause = ""
    if leaders_a:
        leader_clause = (
            f" The top three departments in the first set are "
            f"{', '.join(leaders_a)}; in the second set they are "
            f"{', '.join(leaders_b)}."
        )
    return (
        f"Revenue {direction} from ${total_b:,.1f}k to ${total_a:,.1f}k, a "
        f"change of {pct:+.1f}%.{leader_clause}"
    )


def _sum_revenue(rows: List[Dict[str, Any]]) -> float:
    total = 0.0
    for row in rows:
        v = row.get("revenue_k_usd")
        if isinstance(v, (int, float)):
            total += float(v)
    return total


def _top_departments(rows: List[Dict[str, Any]], k: int) -> List[str]:
    ranked = sorted(
        (r for r in rows if "department" in r and "revenue_k_usd" in r),
        key=lambda r: r["revenue_k_usd"],
        reverse=True,
    )
    return [r["department"] for r in ranked[:k]]


# ---------------------------------------------------------------------------
# Unified dispatcher used by runners that prefer a single entry point
# ---------------------------------------------------------------------------
TOOL_REGISTRY: Dict[str, Callable[..., Any]] = {
    "query_sales_data": query_sales_data,
    "summarize_trend": summarize_trend,
}


@dataclass
class ToolCallRecord:
    """A single tool invocation as observed by the runner.

    Runners emit one of these for every call their framework makes. The
    metrics module aggregates the list to compute success rate, retries, and
    exception rate.
    """

    name: str
    arguments: Dict[str, Any]
    ok: bool
    result_preview: str
    error: Optional[str] = None

    def fingerprint(self) -> str:
        """Stable hash of (name, arguments) for determinism comparisons."""
        payload = json.dumps(
            {"name": self.name, "arguments": self.arguments},
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def dispatch(name: str, arguments: Dict[str, Any]) -> ToolCallRecord:
    """Invoke a tool by name and wrap the result as a :class:`ToolCallRecord`."""
    fn = TOOL_REGISTRY.get(name)
    if fn is None:
        return ToolCallRecord(
            name=name,
            arguments=arguments,
            ok=False,
            result_preview="",
            error=f"unknown tool: {name}",
        )
    try:
        result = fn(**arguments)
    except ToolError as exc:
        return ToolCallRecord(
            name=name,
            arguments=arguments,
            ok=False,
            result_preview="",
            error=str(exc),
        )
    except TypeError as exc:  # wrong kwargs
        return ToolCallRecord(
            name=name,
            arguments=arguments,
            ok=False,
            result_preview="",
            error=f"argument error: {exc}",
        )
    preview = json.dumps(result, default=str)
    if len(preview) > 500:
        preview = preview[:497] + "..."
    return ToolCallRecord(
        name=name,
        arguments=arguments,
        ok=True,
        result_preview=preview,
    )


def serialize_tool_calls(calls: List[ToolCallRecord]) -> List[Dict[str, Any]]:
    """Convert a list of tool-call records to JSON-ready dicts."""
    return [asdict(c) for c in calls]
