"""Deterministic latency-budget analysis for a declared service DAG."""

from latency_budget_analyzer.analyze import analyze
from latency_budget_analyzer.errors import GraphError
from latency_budget_analyzer.models import Analysis

__all__ = ["Analysis", "GraphError", "analyze"]
