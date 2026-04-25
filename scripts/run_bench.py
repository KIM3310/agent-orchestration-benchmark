"""Command-line entry point: ``python -m scripts.run_bench``.

Run the benchmark across any subset of framework runners and emit JSON /
Markdown / HTML reports. Designed to work both in CI (mock LLM) and against
real LLM APIs (``--use-live``).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import List

from src.config import RESULTS_DIR, BenchmarkConfig
from src.fixtures import load_prompts
from src.report import write_all_reports
from src.runner import BenchmarkRunner, write_results
from src.runners.autogen_runner import AutoGenRunner
from src.runners.base import BaseRunner, MockLLM
from src.runners.crewai_runner import CrewAIRunner
from src.runners.langgraph_runner import LangGraphRunner
from src.runners.stage_pilot_style import StagePilotStyleRunner

FRAMEWORK_CHOICES = {
    "stage-pilot-style": StagePilotStyleRunner,
    "langgraph": LangGraphRunner,
    "crewai": CrewAIRunner,
    "autogen": AutoGenRunner,
}


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Run the agent orchestration benchmark.")
    ap.add_argument(
        "--frameworks",
        default="all",
        help="Comma-separated framework names or 'all'. Choices: "
        + ", ".join(FRAMEWORK_CHOICES),
    )
    ap.add_argument("--output", default=str(RESULTS_DIR / "latest.json"))
    ap.add_argument("--use-live", action="store_true", help="Use real LLM APIs instead of mock.")
    ap.add_argument("--model", default=None)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--replay-trials", type=int, default=None)
    ap.add_argument("--report-only", action="store_true", help="Re-render reports from --input")
    ap.add_argument("--input", default=None, help="Path to an existing results JSON.")
    ap.add_argument("--verbose", "-v", action="count", default=0)
    return ap.parse_args(argv)


def _runner_selection(spec: str) -> List[str]:
    if spec.strip().lower() == "all":
        return list(FRAMEWORK_CHOICES)
    names = [n.strip() for n in spec.split(",") if n.strip()]
    for n in names:
        if n not in FRAMEWORK_CHOICES:
            raise SystemExit(f"unknown framework: {n}")
    return names


def _configure_logging(verbosity: int) -> None:
    level = logging.WARNING
    if verbosity == 1:
        level = logging.INFO
    elif verbosity >= 2:
        level = logging.DEBUG
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv)
    _configure_logging(args.verbose)

    if args.report_only:
        return _report_only(args)

    use_mock = not (args.use_live or os.environ.get("USE_MOCK_LLM") == "0")
    if os.environ.get("USE_MOCK_LLM") == "1":
        use_mock = True

    config = BenchmarkConfig(
        use_mock_llm=use_mock,
        model=args.model or BenchmarkConfig().model,
        seed=args.seed or BenchmarkConfig().seed,
        replay_trials=args.replay_trials or BenchmarkConfig().replay_trials,
    )
    llm = MockLLM(seed=config.seed)

    runners: List[BaseRunner] = [
        FRAMEWORK_CHOICES[name](config=config, llm=llm) for name in _runner_selection(args.frameworks)
    ]

    prompts = load_prompts()
    bench = BenchmarkRunner(runners=runners, prompts=prompts, config=config)
    result = bench.run()

    output_path = Path(args.output)
    write_results(result, output_path)
    paths = write_all_reports(result, out_dir=output_path.parent, stem=output_path.stem)
    logging.getLogger(__name__).info("wrote %s", paths)
    print(json.dumps({"written": {k: str(v) for k, v in paths.items()}}, indent=2))
    return 0


def _report_only(args: argparse.Namespace) -> int:
    src = Path(args.input or args.output)
    if not src.exists():
        raise SystemExit(f"results file not found: {src}")
    result = json.loads(src.read_text(encoding="utf-8"))
    paths = write_all_reports(result, out_dir=src.parent, stem=src.stem)
    print(json.dumps({"written": {k: str(v) for k, v in paths.items()}}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
