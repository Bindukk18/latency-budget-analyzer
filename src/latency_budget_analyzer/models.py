from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Service:
    name: str
    latency_ms: float
    depends_on: tuple[str, ...]
    criticality: str = "required"
    owner: str | None = None


@dataclass(frozen=True)
class ParallelCandidate:
    name: str
    services: tuple[str, ...]
    common_dependency: str


@dataclass(frozen=True)
class ServiceGraph:
    name: str
    target_p95_ms: float
    services: dict[str, Service]
    candidates: tuple[ParallelCandidate, ...] = ()


@dataclass(frozen=True)
class ServiceTiming:
    name: str
    start_ms: float
    finish_ms: float
    latency_ms: float
    slack_ms: float
    on_critical_path: bool
    criticality: str


@dataclass(frozen=True)
class ExistingFanout:
    parent: str
    children: tuple[str, ...]
    critical_branch: str


@dataclass(frozen=True)
class ParallelOpportunity:
    name: str
    services: tuple[str, ...]
    baseline_ms: float
    what_if_ms: float
    saving_ms: float


@dataclass(frozen=True)
class HighestRisk:
    service: str
    latency_ms: float
    share_of_target_percent: float
    reason: str


@dataclass(frozen=True)
class Analysis:
    graph_name: str
    target_ms: float
    critical_path: tuple[str, ...]
    critical_path_latency_ms: float
    remaining_budget_ms: float
    utilization_percent: float
    status: str
    timings: tuple[ServiceTiming, ...]
    existing_parallelism: tuple[ExistingFanout, ...]
    opportunities: tuple[ParallelOpportunity, ...]
    highest_risk: HighestRisk | None
    recommendations: tuple[str, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)
