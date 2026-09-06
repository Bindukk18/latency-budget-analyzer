from __future__ import annotations

from pathlib import Path

import yaml

from latency_budget_analyzer.errors import GraphError
from latency_budget_analyzer.models import ParallelCandidate, Service, ServiceGraph

ALLOWED_CRITICALITY = {"required", "optional"}


def load_graph(path: Path | str) -> ServiceGraph:
    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise GraphError(f"file not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise GraphError(f"malformed YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise GraphError("document must be a mapping")
    return parse_graph(raw)


def parse_graph(raw: dict) -> ServiceGraph:
    name = raw.get("name")
    if not name or not isinstance(name, str):
        raise GraphError("name is required")
    if "target_p95_ms" not in raw:
        raise GraphError("target_p95_ms is required")
    try:
        target = float(raw["target_p95_ms"])
    except (TypeError, ValueError) as exc:
        raise GraphError("target_p95_ms must be a number") from exc
    if target <= 0:
        raise GraphError("target_p95_ms must be positive")

    services_raw = raw.get("services")
    if not isinstance(services_raw, dict) or not services_raw:
        raise GraphError("services must be a non-empty mapping")

    services: dict[str, Service] = {}
    for svc_name, body in services_raw.items():
        if not isinstance(svc_name, str) or not svc_name:
            raise GraphError("service names must be non-empty strings")
        if svc_name in services:
            raise GraphError(f"duplicate service name: {svc_name}")
        if not isinstance(body, dict):
            raise GraphError(f"service {svc_name} must be a mapping")
        if "latency_ms" not in body:
            raise GraphError(f"service {svc_name} missing latency_ms")
        try:
            latency = float(body["latency_ms"])
        except (TypeError, ValueError) as exc:
            raise GraphError(f"service {svc_name} latency_ms must be a number") from exc
        if latency < 0:
            raise GraphError(f"service {svc_name} has negative latency")
        deps = body.get("depends_on") or []
        if not isinstance(deps, list) or not all(isinstance(d, str) for d in deps):
            raise GraphError(f"service {svc_name} depends_on must be a list of names")
        if svc_name in deps:
            raise GraphError(f"service {svc_name} depends on itself")
        if len(deps) != len(set(deps)):
            raise GraphError(f"service {svc_name} has duplicate depends_on entries")
        criticality = body.get("criticality", "required")
        if criticality not in ALLOWED_CRITICALITY:
            raise GraphError(f"service {svc_name} has invalid criticality")
        if "parallelizable_with" in body:
            raise GraphError(
                "parallelizable_with is ambiguous; declare parallelization_candidates "
                "with services and common_dependency"
            )
        services[svc_name] = Service(
            name=svc_name,
            latency_ms=latency,
            depends_on=tuple(deps),
            criticality=criticality,
            owner=body.get("owner"),
        )

    for svc in services.values():
        for dep in svc.depends_on:
            if dep not in services:
                raise GraphError(f"unknown dependency {dep} on {svc.name}")

    _reject_cycles(services)
    candidates = _parse_candidates(raw.get("parallelization_candidates") or [], services)
    return ServiceGraph(name=name, target_p95_ms=target, services=services, candidates=candidates)


def _parse_candidates(raw, services: dict[str, Service]) -> tuple[ParallelCandidate, ...]:
    if not isinstance(raw, list):
        raise GraphError("parallelization_candidates must be a list")
    seen: set[str] = set()
    out: list[ParallelCandidate] = []
    for item in raw:
        if not isinstance(item, dict):
            raise GraphError("each parallelization candidate must be a mapping")
        cname = item.get("name")
        if not cname or not isinstance(cname, str):
            raise GraphError("parallelization candidate missing name")
        if cname in seen:
            raise GraphError(f"duplicate parallelization candidate: {cname}")
        seen.add(cname)
        members = item.get("services") or []
        common = item.get("common_dependency")
        if not isinstance(members, list) or len(members) < 2:
            raise GraphError(f"candidate {cname} needs at least two services")
        if not all(isinstance(s, str) for s in members):
            raise GraphError(f"candidate {cname} services must be names")
        if len(members) != len(set(members)):
            raise GraphError(f"candidate {cname} has duplicate services")
        if not isinstance(common, str) or not common:
            raise GraphError(f"candidate {cname} missing common_dependency")
        if common in members:
            raise GraphError(f"candidate {cname} common_dependency cannot be a member")
        for member in members:
            if member not in services:
                raise GraphError(f"candidate {cname} unknown service {member}")
        if common not in services:
            raise GraphError(f"candidate {cname} unknown common_dependency {common}")
        for member in members:
            if not _is_downstream(services, member, common):
                raise GraphError(
                    f"candidate {cname} service {member} is not downstream of {common}"
                )
        candidate = ParallelCandidate(
            name=cname, services=tuple(members), common_dependency=common
        )
        try:
            _reject_cycles(_what_if_services(services, candidate))
        except GraphError as exc:
            raise GraphError(
                f"candidate {cname} what-if transformation creates a cycle"
            ) from exc
        out.append(candidate)
    return tuple(out)


def _is_downstream(services: dict[str, Service], node: str, ancestor: str) -> bool:
    seen: set[str] = set()
    stack = list(services[node].depends_on)
    while stack:
        current = stack.pop()
        if current == ancestor:
            return True
        if current in seen:
            continue
        seen.add(current)
        stack.extend(services[current].depends_on)
    return False


def _what_if_services(
    services: dict[str, Service], candidate: ParallelCandidate
) -> dict[str, Service]:
    members = set(candidate.services)
    common = candidate.common_dependency
    rewritten: dict[str, Service] = {}
    for name, svc in services.items():
        if name not in members:
            rewritten[name] = svc
            continue
        kept = [d for d in svc.depends_on if d not in members]
        if common not in kept:
            kept.append(common)
        rewritten[name] = Service(
            name=name,
            latency_ms=svc.latency_ms,
            depends_on=tuple(kept),
            criticality=svc.criticality,
            owner=svc.owner,
        )
    return rewritten


def _reject_cycles(services: dict[str, Service]) -> None:
    visiting: set[str] = set()
    seen: set[str] = set()

    def dfs(node: str) -> None:
        if node in seen:
            return
        if node in visiting:
            raise GraphError(f"cycle detected at {node}")
        visiting.add(node)
        for dep in services[node].depends_on:
            dfs(dep)
        visiting.remove(node)
        seen.add(node)

    for name in services:
        dfs(name)
