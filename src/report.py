"""Render benchmark results to Markdown, HTML, and JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .config import RESULTS_DIR


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def write_all_reports(
    result: Dict[str, Any], out_dir: Path = RESULTS_DIR, stem: str = "latest"
) -> Dict[str, Path]:
    """Write JSON, Markdown, and HTML reports for a results dict.

    Returns a dict mapping format name to the path written.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "json": out_dir / f"{stem}.json",
        "md": out_dir / f"{stem}.md",
        "html": out_dir / f"{stem}.html",
    }
    paths["json"].write_text(json.dumps(result, indent=2), encoding="utf-8")
    paths["md"].write_text(render_markdown(result), encoding="utf-8")
    paths["html"].write_text(render_html(result), encoding="utf-8")
    return paths


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------
_COLUMNS = [
    ("framework", "Framework"),
    ("tool_call_success_rate", "Tool Success"),
    ("final_answer_quality", "Answer Quality"),
    ("latency_p50_ms", "p50 (ms)"),
    ("latency_p95_ms", "p95 (ms)"),
    ("latency_p99_ms", "p99 (ms)"),
    ("tokens_in", "Tokens In"),
    ("tokens_out", "Tokens Out"),
    ("total_cost_usd", "Cost (USD)"),
    ("retry_count", "Retries"),
    ("exception_rate", "Exception Rate"),
    ("deterministic_replay_rate", "Replay Stability"),
]


def render_markdown(result: Dict[str, Any]) -> str:
    summaries: List[Dict[str, Any]] = result.get("summaries", [])
    header = "| " + " | ".join(col_name for _, col_name in _COLUMNS) + " |"
    sep = "|" + "|".join("---" for _ in _COLUMNS) + "|"
    rows: List[str] = []
    for summary in summaries:
        cells = [_format_cell(summary.get(key, "")) for key, _ in _COLUMNS]
        rows.append("| " + " | ".join(cells) + " |")

    meta = (
        f"**Generated at:** {result.get('generated_at', 'n/a')}  "
        f"\n**Model:** `{result.get('model', 'n/a')}`  "
        f"\n**Prompts:** {result.get('n_prompts', 'n/a')}  "
        f"\n**Replay trials:** {result.get('config', {}).get('replay_trials', 'n/a')}"
    )

    parts = [
        "# Agent Orchestration Benchmark Results",
        "",
        meta,
        "",
        "## Framework Summary",
        "",
        header,
        sep,
        *rows,
        "",
        "## Per-Prompt Observations",
        "",
    ]

    observations: Dict[str, List[Dict[str, Any]]] = result.get("observations", {})
    for framework, obs_list in observations.items():
        parts.append(f"### {framework}")
        parts.append("")
        parts.append("| Prompt | Tool Calls | Latency (ms) | Tokens | Retries |")
        parts.append("|---|---|---|---|---|")
        for obs in obs_list:
            tool_names = ", ".join(c.get("name", "?") for c in obs.get("tool_calls", []))
            parts.append(
                "| {pid} | {tools} | {lat:.1f} | {tin}+{tout} | {retries} |".format(
                    pid=obs.get("prompt_id", "?"),
                    tools=tool_names or "-",
                    lat=obs.get("latency_ms", 0.0),
                    tin=obs.get("tokens_in", 0),
                    tout=obs.get("tokens_out", 0),
                    retries=obs.get("retry_count", 0),
                )
            )
        parts.append("")
    return "\n".join(parts)


def _format_cell(value: Any) -> str:
    if isinstance(value, float):
        if 0.0 <= value <= 1.0:
            return f"{value:.3f}"
        return f"{value:.2f}"
    return str(value)


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------
_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Agent Orchestration Benchmark</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 2rem; color: #222; }}
    h1 {{ border-bottom: 1px solid #ddd; padding-bottom: .4rem; }}
    table {{ border-collapse: collapse; margin-bottom: 2rem; width: 100%; }}
    th, td {{ border: 1px solid #ddd; padding: .5rem .75rem; text-align: right; font-variant-numeric: tabular-nums; }}
    th:first-child, td:first-child {{ text-align: left; font-weight: 600; }}
    thead {{ background: #f6f8fa; }}
    code {{ background: #f6f8fa; padding: .1rem .3rem; border-radius: 3px; }}
  </style>
</head>
<body>
  <h1>Agent Orchestration Benchmark</h1>
  <p><strong>Generated:</strong> {generated}<br>
     <strong>Model:</strong> <code>{model}</code><br>
     <strong>Prompts:</strong> {n_prompts}</p>
  <h2>Framework Summary</h2>
  <table>
    <thead><tr>{header}</tr></thead>
    <tbody>{rows}</tbody>
  </table>
</body>
</html>
"""


def render_html(result: Dict[str, Any]) -> str:
    header_cells = "".join(f"<th>{name}</th>" for _, name in _COLUMNS)
    rows_html = "".join(_render_row(summary) for summary in result.get("summaries", []))
    return _HTML_TEMPLATE.format(
        generated=result.get("generated_at", "n/a"),
        model=result.get("model", "n/a"),
        n_prompts=result.get("n_prompts", "n/a"),
        header=header_cells,
        rows=rows_html,
    )


def _render_row(summary: Dict[str, Any]) -> str:
    cells = "".join(f"<td>{_format_cell(summary.get(key, ''))}</td>" for key, _ in _COLUMNS)
    return f"<tr>{cells}</tr>"


def framework_leaderboard(result: Dict[str, Any]) -> Iterable[str]:
    """Yield framework names sorted by combined quality + stability score.

    Intended for CLI output and convenience scripts.
    """
    summaries: List[Dict[str, Any]] = result.get("summaries", [])
    scored = [
        (
            s["framework"],
            s.get("tool_call_success_rate", 0.0)
            + s.get("final_answer_quality", 0.0)
            + s.get("deterministic_replay_rate", 0.0),
        )
        for s in summaries
    ]
    scored.sort(key=lambda t: t[1], reverse=True)
    return (name for name, _ in scored)
