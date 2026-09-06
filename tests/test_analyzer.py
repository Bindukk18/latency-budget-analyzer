from pathlib import Path

import pytest

from latency_budget_analyzer.analyze import analyze, what_if_graph
from latency_budget_analyzer.cli import main
from latency_budget_analyzer.errors import GraphError
from latency_budget_analyzer.loader import load_graph, parse_graph
from latency_budget_analyzer.report import render_json

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def test_sequential_critical_path_is_sum_of_chain():
    result = analyze(load_graph(EXAMPLES / "sequential.yaml"))
    assert result.critical_path == (
        "gateway",
        "checkout",
        "pricing",
        "inventory",
        "payment",
        "response",
    )
    assert result.critical_path_latency_ms == 275
    assert result.status == "WITHIN_BUDGET"


def test_parallel_branches_use_longest_branch_not_sum():
    result = analyze(load_graph(EXAMPLES / "parallel.yaml"))
    assert result.critical_path == ("gateway", "aggregator", "recommendations", "response")
    assert result.critical_path_latency_ms == 170
    assert result.critical_path_latency_ms != 15 + 25 + 60 + 80 + 110 + 20


def test_remaining_budget_calculated_correctly():
    sequential = analyze(load_graph(EXAMPLES / "sequential.yaml"))
    parallel = analyze(load_graph(EXAMPLES / "parallel.yaml"))
    assert sequential.remaining_budget_ms == 25
    assert abs(sequential.utilization_percent - 91.6667) < 0.01
    assert parallel.remaining_budget_ms == 80
    assert abs(parallel.utilization_percent - 68.0) < 0.01


def test_over_budget_returns_exceeded_status():
    result = analyze(load_graph(EXAMPLES / "over-budget.yaml"))
    assert result.status == "BUDGET_EXCEEDED"
    assert result.remaining_budget_ms == -20


def test_highest_risk_is_largest_critical_path_dependency():
    result = analyze(load_graph(EXAMPLES / "parallel.yaml"))
    assert result.highest_risk is not None
    assert result.highest_risk.service == "recommendations"
    assert result.highest_risk.latency_ms == 110
    assert abs(result.highest_risk.share_of_target_percent - 44.0) < 0.05


def test_non_critical_slow_service_has_slack():
    result = analyze(load_graph(EXAMPLES / "parallel.yaml"))
    by_name = {row.name: row for row in result.timings}
    assert by_name["profile"].slack_ms == 50
    assert by_name["catalog"].slack_ms == 30
    assert by_name["recommendations"].slack_ms == 0
    assert by_name["profile"].on_critical_path is False


def test_optimizing_within_slack_does_not_change_critical_path():
    graph = load_graph(EXAMPLES / "parallel.yaml")
    services = dict(graph.services)
    profile = services["profile"]
    services["profile"] = type(profile)(
        name=profile.name,
        latency_ms=30,
        depends_on=profile.depends_on,
        criticality=profile.criticality,
        owner=profile.owner,
    )
    faster = type(graph)(
        name=graph.name,
        target_p95_ms=graph.target_p95_ms,
        services=services,
        candidates=graph.candidates,
    )
    original = analyze(graph)
    reduced = analyze(faster)
    assert reduced.critical_path == original.critical_path
    assert reduced.critical_path_latency_ms == original.critical_path_latency_ms


def test_explicit_parallelization_opportunity_shows_expected_saving():
    result = analyze(load_graph(EXAMPLES / "parallelization-opportunity.yaml"))
    assert result.critical_path_latency_ms == 260
    assert result.status == "BUDGET_EXCEEDED"
    assert result.remaining_budget_ms == -40
    assert len(result.opportunities) == 1
    opp = result.opportunities[0]
    assert opp.saving_ms == 60
    assert opp.what_if_ms == 200
    assert opp.baseline_ms == 260


def test_undeclared_parallelism_is_never_invented():
    result = analyze(load_graph(EXAMPLES / "sequential.yaml"))
    assert result.opportunities == ()
    assert result.existing_parallelism == ()


def test_parallelization_preserves_unrelated_dependencies():
    graph = parse_graph(
        {
            "name": "preserve-deps",
            "target_p95_ms": 500,
            "services": {
                "checkout": {"latency_ms": 10, "depends_on": []},
                "tax-config": {"latency_ms": 15, "depends_on": []},
                "inventory-policy": {"latency_ms": 100, "depends_on": []},
                "pricing": {
                    "latency_ms": 60,
                    "depends_on": ["checkout", "tax-config"],
                },
                "inventory": {
                    "latency_ms": 80,
                    "depends_on": ["pricing", "inventory-policy"],
                },
                "payment": {"latency_ms": 10, "depends_on": ["inventory"]},
            },
            "parallelization_candidates": [
                {
                    "name": "pricing-inventory",
                    "services": ["pricing", "inventory"],
                    "common_dependency": "checkout",
                }
            ],
        }
    )
    assert graph.services["pricing"].depends_on == ("checkout", "tax-config")
    assert graph.services["inventory"].depends_on == ("pricing", "inventory-policy")

    altered = what_if_graph(graph, graph.candidates[0])
    assert graph.services["pricing"].depends_on == ("checkout", "tax-config")
    assert graph.services["inventory"].depends_on == ("pricing", "inventory-policy")
    assert altered.services["pricing"].depends_on == ("checkout", "tax-config")
    assert "pricing" not in altered.services["inventory"].depends_on
    assert set(altered.services["inventory"].depends_on) == {"checkout", "inventory-policy"}

    result = analyze(graph)
    # Dropping inventory-policy would let inventory start at checkout (10)
    # and finish at 90; payment would finish at 100. Preserving it keeps
    # inventory start at 100, payment at 190.
    assert result.opportunities[0].what_if_ms == 190
    assert result.opportunities[0].baseline_ms == 190


def test_parallelization_not_on_critical_path_shows_zero_saving():
    graph = parse_graph(
        {
            "name": "zero-save",
            "target_p95_ms": 500,
            "services": {
                "src": {"latency_ms": 10, "depends_on": []},
                "slow": {"latency_ms": 200, "depends_on": ["src"]},
                "a": {"latency_ms": 20, "depends_on": ["src"]},
                "b": {"latency_ms": 25, "depends_on": ["a"]},
                "sink": {"latency_ms": 10, "depends_on": ["slow", "b"]},
            },
            "parallelization_candidates": [
                {
                    "name": "a-b",
                    "services": ["a", "b"],
                    "common_dependency": "src",
                }
            ],
        }
    )
    result = analyze(graph)
    assert result.opportunities[0].saving_ms == 0


def test_cycle_is_rejected():
    with pytest.raises(GraphError, match="cycle"):
        parse_graph(
            {
                "name": "cyc",
                "target_p95_ms": 100,
                "services": {
                    "a": {"latency_ms": 1, "depends_on": ["b"]},
                    "b": {"latency_ms": 1, "depends_on": ["a"]},
                },
            }
        )


def test_unknown_dependency_is_rejected():
    with pytest.raises(GraphError, match="unknown dependency"):
        parse_graph(
            {
                "name": "unk",
                "target_p95_ms": 100,
                "services": {"a": {"latency_ms": 1, "depends_on": ["ghost"]}},
            }
        )


def test_negative_latency_is_rejected():
    with pytest.raises(GraphError, match="negative"):
        parse_graph(
            {
                "name": "neg",
                "target_p95_ms": 100,
                "services": {"a": {"latency_ms": -1, "depends_on": []}},
            }
        )


def test_deterministic_tie_selects_stable_critical_path():
    graph = parse_graph(
        {
            "name": "tie",
            "target_p95_ms": 200,
            "services": {
                "src": {"latency_ms": 10, "depends_on": []},
                "alpha": {"latency_ms": 50, "depends_on": ["src"]},
                "beta": {"latency_ms": 50, "depends_on": ["src"]},
                "sink": {"latency_ms": 10, "depends_on": ["alpha", "beta"]},
            },
        }
    )
    first = analyze(graph)
    second = analyze(graph)
    assert first.critical_path == second.critical_path
    assert first.critical_path == ("src", "alpha", "sink")


def test_json_output_is_deterministic():
    result = analyze(load_graph(EXAMPLES / "parallel.yaml"))
    assert render_json(result) == render_json(result)


def test_cli_within_budget_returns_exit_0():
    assert main(["analyze", str(EXAMPLES / "sequential.yaml")]) == 0


def test_cli_exceeded_budget_returns_exit_1():
    assert main(["analyze", str(EXAMPLES / "over-budget.yaml")]) == 1


def test_cli_invalid_graph_returns_exit_2(tmp_path, capsys):
    bad = tmp_path / "bad.yaml"
    bad.write_text("name: x\n", encoding="utf-8")
    assert main(["analyze", str(bad)]) == 2
    err = capsys.readouterr().err
    assert "error:" in err


def test_what_if_does_not_mutate_baseline():
    graph = load_graph(EXAMPLES / "parallelization-opportunity.yaml")
    before = graph.services["inventory"].depends_on
    what_if_graph(graph, graph.candidates[0])
    assert graph.services["inventory"].depends_on == before
