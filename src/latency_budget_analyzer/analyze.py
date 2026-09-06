from __future__ import annotations

from collections import defaultdict

from latency_budget_analyzer.loader import _what_if_services
from latency_budget_analyzer.models import (
    Analysis,
    ExistingFanout,
    HighestRisk,
    ParallelCandidate,
    ParallelOpportunity,
    Service,
    ServiceGraph,
    ServiceTiming,
)


def analyze(graph: ServiceGraph) -> Analysis:
    schedule = _schedule(graph.services)
    critical_path, latency = _critical_path(graph.services, schedule)
    remaining = graph.target_p95_ms - latency
    utilization = (latency / graph.target_p95_ms) * 100.0
    status = _status(remaining)
    timings = _timings(graph.services, schedule, set(critical_path), latency)
    fanouts = _existing_fanout(graph.services, schedule, critical_path)
    opportunities = _opportunities(graph, latency)
    risk = _highest_risk(graph.services, critical_path, graph.target_p95_ms)
    recs = _recommendations(graph, timings, critical_path, opportunities, risk)
    warnings = _warnings(graph)
    return Analysis(
        graph_name=graph.name,
        target_ms=graph.target_p95_ms,
        critical_path=critical_path,
        critical_path_latency_ms=latency,
        remaining_budget_ms=remaining,
        utilization_percent=utilization,
        status=status,
        timings=timings,
        existing_parallelism=fanouts,
        opportunities=opportunities,
        highest_risk=risk,
        recommendations=recs,
        warnings=warnings,
    )


def what_if_graph(graph: ServiceGraph, candidate: ParallelCandidate) -> ServiceGraph:
    """Copy the graph and drop only intra-candidate serialization edges.

    Unrelated depends_on entries are kept. common_dependency is added
    only if it is not already a direct dependency after that removal.
    The baseline graph and its Service objects are not mutated.
    """
    return ServiceGraph(
        name=graph.name,
        target_p95_ms=graph.target_p95_ms,
        services=_what_if_services(graph.services, candidate),
        candidates=(),
    )


def _schedule(services: dict[str, Service]) -> dict[str, tuple[float, float]]:
    """Forward pass: start = max(parent finish), finish = start + latency."""
    order = _topo(services)
    start: dict[str, float] = {}
    finish: dict[str, float] = {}
    for name in order:
        preds = services[name].depends_on
        start[name] = max((finish[p] for p in preds), default=0.0)
        finish[name] = start[name] + services[name].latency_ms
    return {name: (start[name], finish[name]) for name in services}


def _critical_path(
    services: dict[str, Service],
    schedule: dict[str, tuple[float, float]],
) -> tuple[tuple[str, ...], float]:
    """Lex-smallest longest path. Paths stored during the forward sweep."""
    order = _topo(services)
    path: dict[str, tuple[str, ...]] = {}
    for name in order:
        preds = services[name].depends_on
        if not preds:
            path[name] = (name,)
            continue
        max_finish = max(schedule[p][1] for p in preds)
        candidates = [p for p in preds if schedule[p][1] == max_finish]
        chosen = min(candidates, key=lambda p: path[p])
        path[name] = path[chosen] + (name,)
    latency = max(schedule[n][1] for n in services)
    sinks = [n for n in services if schedule[n][1] == latency]
    chosen_sink = min(sinks, key=lambda n: path[n])
    return path[chosen_sink], latency


def _slack(
    services: dict[str, Service],
    schedule: dict[str, tuple[float, float]],
    graph_finish: float,
) -> dict[str, float]:
    """Backward pass: latest start that does not extend graph_finish."""
    successors: dict[str, list[str]] = defaultdict(list)
    for name, svc in services.items():
        for pred in svc.depends_on:
            successors[pred].append(name)
    latest_start: dict[str, float] = {}
    latest_finish: dict[str, float] = {}
    for name in reversed(_topo(services)):
        kids = successors[name]
        if kids:
            latest_finish[name] = min(latest_start[k] for k in kids)
        else:
            latest_finish[name] = graph_finish
        latest_start[name] = latest_finish[name] - services[name].latency_ms
    return {n: latest_start[n] - schedule[n][0] for n in services}


def _timings(
    services: dict[str, Service],
    schedule: dict[str, tuple[float, float]],
    critical: set[str],
    graph_finish: float,
) -> tuple[ServiceTiming, ...]:
    slack = _slack(services, schedule, graph_finish)
    rows = []
    for name in sorted(services, key=lambda n: (schedule[n][0], n)):
        start, finish = schedule[name]
        rows.append(
            ServiceTiming(
                name=name,
                start_ms=start,
                finish_ms=finish,
                latency_ms=services[name].latency_ms,
                slack_ms=slack[name],
                on_critical_path=name in critical,
                criticality=services[name].criticality,
            )
        )
    return tuple(rows)


def _existing_fanout(
    services: dict[str, Service],
    schedule: dict[str, tuple[float, float]],
    critical_path: tuple[str, ...],
) -> tuple[ExistingFanout, ...]:
    children: dict[str, list[str]] = defaultdict(list)
    for name, svc in services.items():
        for pred in svc.depends_on:
            children[pred].append(name)
    critical_set = set(critical_path)
    fanouts: list[ExistingFanout] = []
    for parent, kids in children.items():
        if len(kids) < 2:
            continue
        _, parent_finish = schedule[parent]
        concurrent = [k for k in kids if schedule[k][0] == parent_finish]
        if len(concurrent) < 2:
            continue
        concurrent.sort()
        on_path = [k for k in concurrent if k in critical_set]
        branch = on_path[0] if on_path else max(concurrent, key=lambda k: schedule[k][1])
        fanouts.append(
            ExistingFanout(parent=parent, children=tuple(concurrent), critical_branch=branch)
        )
    fanouts.sort(key=lambda f: f.parent)
    return tuple(fanouts)


def _opportunities(graph: ServiceGraph, baseline: float) -> tuple[ParallelOpportunity, ...]:
    rows: list[ParallelOpportunity] = []
    for candidate in graph.candidates:
        altered = what_if_graph(graph, candidate)
        _, what_if = _critical_path(altered.services, _schedule(altered.services))
        rows.append(
            ParallelOpportunity(
                name=candidate.name,
                services=candidate.services,
                baseline_ms=baseline,
                what_if_ms=what_if,
                saving_ms=baseline - what_if,
            )
        )
    rows.sort(key=lambda r: (-r.saving_ms, r.name))
    return tuple(rows)


def _highest_risk(
    services: dict[str, Service],
    critical_path: tuple[str, ...],
    target: float,
) -> HighestRisk | None:
    if not critical_path:
        return None
    successors: dict[str, list[str]] = defaultdict(list)
    for name, svc in services.items():
        for pred in svc.depends_on:
            successors[pred].append(name)
    internals = [
        n
        for n in critical_path
        if services[n].depends_on and successors[n]
    ]
    pool = internals or list(critical_path)
    best = max(services[n].latency_ms for n in pool)
    chosen = min(n for n in pool if services[n].latency_ms == best)
    share = (services[chosen].latency_ms / target) * 100.0 if target else 0.0
    return HighestRisk(
        service=chosen,
        latency_ms=services[chosen].latency_ms,
        share_of_target_percent=share,
        reason="largest individual latency contribution on selected critical path",
    )


def _recommendations(
    graph: ServiceGraph,
    timings: tuple[ServiceTiming, ...],
    critical_path: tuple[str, ...],
    opportunities: tuple[ParallelOpportunity, ...],
    risk: HighestRisk | None,
) -> tuple[str, ...]:
    recs: list[str] = []
    if risk:
        recs.append(
            f"{risk.service} contributes {risk.share_of_target_percent:.0f}% of the "
            "latency target and lies on the critical path."
        )
    for timing in timings:
        if timing.slack_ms > 0:
            recs.append(
                f"{timing.name} has {timing.slack_ms:g} ms of slack; optimizing it by "
                "less than that will not reduce current end-to-end critical-path latency."
            )
    for opp in opportunities:
        names = " + ".join(opp.services)
        if opp.saving_ms > 0:
            recs.append(
                f"{names} are explicitly declared parallelizable; what-if analysis "
                f"reduces critical path by {opp.saving_ms:g} ms."
            )
        else:
            recs.append(
                f"{names} are explicitly declared parallelizable but yield "
                "0 ms critical-path improvement."
            )
    for name in critical_path:
        svc = graph.services[name]
        if svc.criticality == "optional":
            recs.append(
                f"{name} is optional but lies on the critical path; consider a "
                "fallback only if product semantics permit."
            )
    recs.append(
        "OPTIMIZING A NON-CRITICAL SERVICE MAY PRODUCE ZERO END-TO-END LATENCY IMPROVEMENT."
    )
    return tuple(recs)


def _warnings(graph: ServiceGraph) -> tuple[str, ...]:
    notes = [
        "This is deterministic budget analysis over supplied service values.",
        "SUM OF SERVICE P95s != TRUE END-TO-END P95.",
    ]
    optionals = [n for n, s in graph.services.items() if s.criticality == "optional"]
    if optionals:
        notes.append(
            "optional services remain in the graph; they are not dropped automatically."
        )
    return tuple(notes)


def _status(remaining: float) -> str:
    if remaining < 0:
        return "BUDGET_EXCEEDED"
    if remaining == 0:
        return "AT_BUDGET"
    return "WITHIN_BUDGET"


def _topo(services: dict[str, Service]) -> list[str]:
    incoming = {name: set(svc.depends_on) for name, svc in services.items()}
    ready = sorted(name for name, preds in incoming.items() if not preds)
    order: list[str] = []
    children: dict[str, list[str]] = defaultdict(list)
    for name, svc in services.items():
        for pred in svc.depends_on:
            children[pred].append(name)
    while ready:
        node = ready.pop(0)
        order.append(node)
        for child in sorted(children[node]):
            incoming[child].remove(node)
            if not incoming[child]:
                ready.append(child)
                ready.sort()
    if len(order) != len(services):
        raise RuntimeError("cycle survived validation")
    return order
