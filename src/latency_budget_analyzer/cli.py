from __future__ import annotations

import argparse
import sys
from pathlib import Path

from latency_budget_analyzer.analyze import analyze
from latency_budget_analyzer.errors import GraphError
from latency_budget_analyzer.loader import load_graph
from latency_budget_analyzer.report import render_json, render_text

EXIT_OK = 0
EXIT_EXCEEDED = 1
EXIT_INVALID = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="latency-budget-analyzer",
        description="Deterministic latency-budget analysis over a YAML service DAG.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    analyze_p = sub.add_parser("analyze", help="analyze a service graph")
    analyze_p.add_argument("path", type=Path)
    analyze_p.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command != "analyze":
        parser.error("unknown command")
    try:
        graph = load_graph(args.path)
        result = analyze(graph)
    except GraphError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_INVALID
    text = render_json(result) if args.format == "json" else render_text(result)
    sys.stdout.write(text)
    if result.status == "BUDGET_EXCEEDED":
        return EXIT_EXCEEDED
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
