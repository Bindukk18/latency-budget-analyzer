# Algorithm

1. Validate YAML and that `depends_on` forms a DAG.
2. Kahn topological order (lex-stable ready queue).
3. **Forward pass:** `start = max(parent.finish)` or 0; `finish = start + latency`.
4. Graph latency = max finish over all nodes (sinks determine it).
5. **Critical path:** while sweeping forward, keep the lex-smallest path
   that achieves each node's finish. Among nodes at the global max finish,
   take the lex-smallest path. Ties are therefore deterministic.
6. **Backward pass:** `latest_finish(sink) = T`; for others
   `latest_finish = min(latest_start of successors)`;
   `latest_start = latest_finish - latency`;
   `slack = latest_start - earliest_start`.
7. Remaining budget = target − critical-path latency.
8. For each declared `parallelization_candidates` entry, copy the graph.
   Remove only dependency edges *between* listed candidate services.
   Keep every unrelated `depends_on`. Ensure `common_dependency` remains
   a direct predecessor of each candidate service (add it if the removed
   edge was the only path to it). Recompute the longest path on that
   copy. Rank by saving descending, then name.

## Complexity

V services, E edges, P explicit candidates.

Baseline analysis: **O(V + E)** plus **O(V)** path storage per node
(path tuples are copied along the sweep, so path materialization is
**O(V²)** in the worst chain).

Each what-if: another **O(V + E)** (plus path copies). Total
**O(P × (V + E))** plus path-copy overhead. Graphs in this tool are
expected to stay small.
