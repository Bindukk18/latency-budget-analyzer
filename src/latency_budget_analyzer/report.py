from __future__ import annotations

import json

from latency_budget_analyzer.models import Analysis


def render_text(analysis: Analysis) -> str:
    path = " -> ".join(analysis.critical_path)
    remaining = analysis.remaining_budget_ms
    rem_s = f"{remaining:g} ms" if remaining >= 0 else f"{remaining:g} ms"
    lines = [
        "LATENCY BUDGET ANALYSIS",
        "=======================",
        "",
        f"Graph: {analysis.graph_name}",
        f"Target p95 budget: {analysis.target_ms:g} ms",
        "",
        "Critical path:",
        path,
        "",
        f"Critical-path latency: {analysis.critical_path_latency_ms:g} ms",
        f"Remaining budget:      {rem_s}",
        f"Budget utilization:    {analysis.utilization_percent:.1f}%",
        f"Status:                {analysis.status}",
        "",
        "SERVICE TIMING",
        "--------------",
    ]
    for row in analysis.timings:
        flag = "  critical" if row.on_critical_path else ""
        opt = "  optional" if row.criticality == "optional" else ""
        lines.append(
            f"{row.name:<18} start={row.start_ms:<6g} finish={row.finish_ms:<6g} "
            f"latency={row.latency_ms:<6g} slack={row.slack_ms:g}{flag}{opt}"
        )
    lines.append("")
    lines.append("Existing parallel fan-out:")
    if analysis.existing_parallelism:
        for fan in analysis.existing_parallelism:
            kids = ", ".join(fan.children)
            lines.append(f"{fan.parent} -> [{kids}]")
            lines.append(f"Critical branch: {fan.critical_branch}")
    else:
        lines.append("none")
    lines.append("")
    lines.append("Highest latency-budget risk:")
    if analysis.highest_risk:
        risk = analysis.highest_risk
        lines.append(risk.service)
        lines.append(f"{risk.latency_ms:g} ms / {risk.share_of_target_percent:.1f}% of target")
        lines.append(f"Reason: {risk.reason}")
    else:
        lines.append("none")
    lines.append("")
    lines.append("Parallelization opportunities:")
    if analysis.opportunities:
        lines.append(f"{'Opportunity':<32} Saving")
        for opp in analysis.opportunities:
            label = " + ".join(opp.services)
            lines.append(f"{label:<32} {opp.saving_ms:g} ms")
            lines.append(
                f"  baseline={opp.baseline_ms:g} ms  what-if={opp.what_if_ms:g} ms"
            )
    else:
        lines.append("none declared")
    lines.append("")
    lines.append("Recommendations:")
    for rec in analysis.recommendations:
        lines.append(f"- {rec}")
    lines.append("")
    lines.append("Note:")
    for warn in analysis.warnings:
        lines.append(warn)
    lines.append("It is not a statistical prediction of end-to-end production p95.")
    lines.append("")
    return "\n".join(lines)


def render_json(analysis: Analysis) -> str:
    payload = {
        "graph_name": analysis.graph_name,
        "target_ms": analysis.target_ms,
        "critical_path": list(analysis.critical_path),
        "critical_path_latency_ms": analysis.critical_path_latency_ms,
        "remaining_budget_ms": analysis.remaining_budget_ms,
        "utilization_percent": analysis.utilization_percent,
        "status": analysis.status,
        "services": [
            {
                "name": row.name,
                "start_ms": row.start_ms,
                "finish_ms": row.finish_ms,
                "latency_ms": row.latency_ms,
                "slack_ms": row.slack_ms,
                "on_critical_path": row.on_critical_path,
                "criticality": row.criticality,
            }
            for row in analysis.timings
        ],
        "existing_parallelism": [
            {
                "parent": fan.parent,
                "children": list(fan.children),
                "critical_branch": fan.critical_branch,
            }
            for fan in analysis.existing_parallelism
        ],
        "parallelization_opportunities": [
            {
                "name": opp.name,
                "services": list(opp.services),
                "baseline_ms": opp.baseline_ms,
                "what_if_ms": opp.what_if_ms,
                "saving_ms": opp.saving_ms,
            }
            for opp in analysis.opportunities
        ],
        "highest_risk": None
        if analysis.highest_risk is None
        else {
            "service": analysis.highest_risk.service,
            "latency_ms": analysis.highest_risk.latency_ms,
            "share_of_target_percent": analysis.highest_risk.share_of_target_percent,
            "reason": analysis.highest_risk.reason,
        },
        "warnings": list(analysis.warnings),
        "recommendations": list(analysis.recommendations),
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"
