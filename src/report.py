"""Render benchmark results to Markdown, HTML, and JSON."""

from __future__ import annotations

import html
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

    _, mode_label, mode_description = _execution_mode(result)
    meta = (
        f"**Generated at:** {result.get('generated_at', 'n/a')}  "
        f"\n**Model:** `{result.get('model', 'n/a')}`  "
        f"\n**Prompts:** {result.get('n_prompts', 'n/a')}  "
        f"\n**Replay trials:** {result.get('config', {}).get('replay_trials', 'n/a')}  "
        f"\n**Execution mode:** **{mode_label}** - {mode_description}"
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
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Agent Orchestration Benchmark</title>
  <style>
    :root {{ color-scheme: light; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 2rem auto; max-width: 1440px; padding: 0 1rem; color: #222; line-height: 1.45; }}
    h1 {{ border-bottom: 1px solid #ddd; padding-bottom: .4rem; }}
    h2 {{ margin-top: 2.25rem; }}
    h3 {{ margin-top: 1.75rem; }}
    table {{ border-collapse: collapse; margin-bottom: 2rem; width: 100%; }}
    th, td {{ border: 1px solid #ddd; padding: .5rem .75rem; text-align: right; font-variant-numeric: tabular-nums; vertical-align: top; }}
    th:first-child, td:first-child {{ text-align: left; font-weight: 600; }}
    thead {{ background: #f6f8fa; }}
    code {{ background: #f6f8fa; padding: .1rem .3rem; border-radius: 3px; overflow-wrap: anywhere; }}
    pre {{ background: #f6f8fa; border: 1px solid #e5e7eb; padding: .65rem; overflow: auto; white-space: pre-wrap; word-break: break-word; }}
    details {{ margin: .35rem 0; }}
    summary {{ cursor: pointer; font-weight: 600; }}
    .mode {{ border-left: 4px solid; padding: .75rem 1rem; }}
    .mode-mock {{ background: #fff8e1; border-color: #d97706; }}
    .mode-live {{ background: #ecfdf5; border-color: #059669; }}
    .mode-unknown {{ background: #f3f4f6; border-color: #6b7280; }}
    .evidence-table {{ table-layout: fixed; }}
    .evidence-table th, .evidence-table td {{ text-align: left; font-weight: 400; }}
    .evidence-table th:nth-child(1) {{ width: 24%; }}
    .evidence-table th:nth-child(2) {{ width: 20%; }}
    .evidence-table th:nth-child(3) {{ width: 30%; }}
    .evidence-table th:nth-child(4) {{ width: 26%; }}
    .label {{ display: block; font-size: .75rem; font-weight: 700; margin-top: .5rem; text-transform: uppercase; color: #4b5563; }}
    .status {{ display: inline-block; margin-top: .5rem; padding: .1rem .35rem; border: 1px solid; font-size: .75rem; font-weight: 700; }}
    .pass {{ color: #047857; border-color: #047857; }}
    .fail {{ color: #b91c1c; border-color: #b91c1c; }}
    .unknown {{ color: #6b7280; border-color: #6b7280; }}
    .muted {{ color: #6b7280; }}
    .prompt-text {{ margin-top: .4rem; white-space: pre-wrap; }}
    .trace {{ border-top: 1px solid #e5e7eb; padding-top: .35rem; }}
    @media (max-width: 900px) {{
      body {{ margin-top: 1rem; }}
      .summary-wrap, .evidence-wrap {{ overflow-x: auto; }}
      .summary-table {{ min-width: 1100px; }}
      .evidence-table {{ min-width: 1000px; }}
    }}
  </style>
</head>
<body>
  <h1>Agent Orchestration Benchmark</h1>
  <p><strong>Generated:</strong> {generated}<br>
     <strong>Model:</strong> <code>{model}</code><br>
     <strong>Prompts:</strong> {n_prompts}</p>
  <p class="mode mode-{mode_class}"><strong>Execution mode: {mode_label}</strong><br>
     {mode_description}<br><span class="muted">Mode basis: <code>{mode_source}</code></span></p>
  <h2>Framework Summary</h2>
  <div class="summary-wrap">
    <table class="summary-table">
      <thead><tr>{header}</tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
  <h2>Prompt-Level Evidence</h2>
  <p>Each row preserves the prompt contract captured at run time and the complete observed tool trace used to interpret the aggregate metrics.</p>
  {evidence}
</body>
</html>
"""


def render_html(result: Dict[str, Any]) -> str:
    mode_class, mode_label, mode_description = _execution_mode(result)
    header_cells = "".join(f"<th>{html.escape(name)}</th>" for _, name in _COLUMNS)
    rows_html = "".join(_render_row(summary) for summary in result.get("summaries", []))
    return _HTML_TEMPLATE.format(
        generated=_escape(result.get("generated_at", "n/a")),
        model=_escape(result.get("model", "n/a")),
        n_prompts=_escape(result.get("n_prompts", "n/a")),
        mode_class=mode_class,
        mode_label=mode_label,
        mode_description=mode_description,
        mode_source=_escape(result.get("execution_mode_source", "legacy result inference")),
        header=header_cells,
        rows=rows_html,
        evidence=_render_prompt_evidence(result),
    )


def _render_row(summary: Dict[str, Any]) -> str:
    cells = "".join(
        f"<td>{_escape(_format_cell(summary.get(key, '')))}</td>" for key, _ in _COLUMNS
    )
    return f"<tr>{cells}</tr>"


def _execution_mode(result: Dict[str, Any]) -> tuple[str, str, str]:
    mode = result.get("execution_mode")
    if mode not in {"mock", "live"}:
        configured = result.get("config", {}).get("use_mock_llm")
        mode = "mock" if configured is True else "live" if configured is False else "unknown"
    if mode == "mock":
        return (
            "mock",
            "MOCK / SYNTHETIC",
            "Deterministic local fixtures and a mock LLM produced this run. "
            "Use it for regression evidence, not provider-performance claims.",
        )
    if mode == "live":
        return (
            "live",
            "LIVE / CONFIGURED",
            "The configuration requested each adapter's live path. This label alone "
            "does not prove provider traffic; verify exceptions, tokens, and provider logs.",
        )
    return (
        "unknown",
        "UNKNOWN / LEGACY",
        "This result predates explicit execution-mode metadata; do not infer mock or live.",
    )


def _render_prompt_evidence(result: Dict[str, Any]) -> str:
    contracts = {
        str(contract.get("prompt_id")): contract
        for contract in result.get("prompt_contracts", [])
        if isinstance(contract, dict) and contract.get("prompt_id") is not None
    }
    observations = result.get("observations", {})
    if not isinstance(observations, dict) or not observations:
        return '<p class="muted">No per-prompt observations were captured.</p>'

    sections: List[str] = []
    for framework, raw_observations in observations.items():
        rows: List[str] = []
        obs_list = raw_observations if isinstance(raw_observations, list) else []
        for observation in obs_list:
            if not isinstance(observation, dict):
                continue
            prompt_id = str(observation.get("prompt_id", "?"))
            rows.append(_render_evidence_row(observation, contracts.get(prompt_id)))
        sections.append(
            "<section>"
            f"<h3>{_escape(framework)}</h3>"
            '<div class="evidence-wrap"><table class="evidence-table">'
            "<thead><tr><th>Prompt contract</th><th>Sequence comparison</th>"
            "<th>Observed tool evidence</th><th>Outcome evidence</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table></div>"
            "</section>"
        )
    return "".join(sections)


def _render_evidence_row(observation: Dict[str, Any], contract: Dict[str, Any] | None) -> str:
    prompt_id = observation.get("prompt_id", "?")
    if contract is None:
        prompt_contract = (
            f"<code>{_escape(prompt_id)}</code>"
            '<p class="muted">Prompt contract is unavailable in this legacy result.</p>'
        )
        expected: List[str] | None = None
    else:
        expected = [str(name) for name in contract.get("expected_tool_sequence", [])]
        keywords = ", ".join(str(value) for value in contract.get("answer_keywords", [])) or "-"
        answer_regex = contract.get("answer_regex") or "-"
        prompt_contract = (
            f"<code>{_escape(prompt_id)}</code>"
            f' <span class="muted">{_escape(contract.get("difficulty", "n/a"))}</span>'
            f'<div class="prompt-text">{_escape(contract.get("user_message", ""))}</div>'
            '<span class="label">Answer contract</span>'
            f"Keywords: <code>{_escape(keywords)}</code><br>"
            f"Regex: <code>{_escape(answer_regex)}</code>"
        )

    raw_calls = observation.get("tool_calls", [])
    calls = raw_calls if isinstance(raw_calls, list) else []
    observed = [str(call.get("name", "?")) for call in calls if isinstance(call, dict)]
    all_attempts_ok = all(call.get("ok") is True for call in calls if isinstance(call, dict))
    expected_html = _render_sequence(expected) if expected is not None else "unavailable"
    observed_html = _render_sequence(observed)
    if expected is None:
        status = '<span class="status unknown">NOT SCORED</span>'
    elif observed == expected and all_attempts_ok:
        status = '<span class="status pass">EXACT MATCH</span>'
    else:
        status = '<span class="status fail">MISMATCH</span>'
    sequence = (
        '<span class="label">Expected</span>'
        f"{expected_html}"
        '<span class="label">Observed attempted calls</span>'
        f"{observed_html}<br>{status}"
    )

    traces = "".join(_render_tool_trace(index, call) for index, call in enumerate(calls, 1))
    if not traces:
        traces = '<span class="muted">No tool calls observed.</span>'

    final_answer = observation.get("final_answer") or ""
    exception = observation.get("exception") or ""
    fingerprints = observation.get("replay_fingerprints", [])
    exception_html = _escape(exception) if exception else '<span class="muted">None</span>'
    outcome = (
        "<details><summary>Final answer</summary>"
        f"<pre>{_escape(final_answer) if final_answer else '(empty)'}</pre></details>"
        '<span class="label">Exception</span>'
        f"{exception_html}"
        '<span class="label">Replay fingerprints</span>'
        f"<code>{_escape(_pretty_json(fingerprints))}</code>"
    )
    return (
        "<tr>"
        f"<td>{prompt_contract}</td>"
        f"<td>{sequence}</td>"
        f"<td>{traces}</td>"
        f"<td>{outcome}</td>"
        "</tr>"
    )


def _render_tool_trace(index: int, raw_call: Any) -> str:
    if not isinstance(raw_call, dict):
        return (
            '<details class="trace"><summary>'
            f"#{index} invalid trace record</summary><pre>{_escape(raw_call)}</pre></details>"
        )
    name = raw_call.get("name", "?")
    ok = raw_call.get("ok") is True
    status = "OK" if ok else "FAILED"
    status_class = "pass" if ok else "fail"
    evidence = raw_call.get("result_preview") if ok else raw_call.get("error")
    return (
        '<details class="trace">'
        f"<summary>#{index} {_escape(name)} "
        f'<span class="status {status_class}">{status}</span></summary>'
        '<span class="label">Arguments</span>'
        f"<pre>{_escape(_pretty_json(raw_call.get('arguments', {})))}</pre>"
        '<span class="label">Result / error</span>'
        f"<pre>{_escape(evidence) if evidence else '(empty)'}</pre>"
        "</details>"
    )


def _render_sequence(names: List[str] | None) -> str:
    if not names:
        return '<span class="muted">None</span>'
    return " &rarr; ".join(f"<code>{_escape(name)}</code>" for name in names)


def _pretty_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return str(value)


def _escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


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
