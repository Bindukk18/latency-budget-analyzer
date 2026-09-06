# Interpretation

Critical-path latency is a **budget estimate** using supplied values,
not a predicted production p95.

Percentiles do not add. Even if every `latency_ms` is an observed p95,
their longest-path sum is not the end-to-end p95.

Highest latency-budget risk = largest non-entry/non-terminal service on
the selected critical path (lex-smallest name on a tie). It is **not**
incident probability.

Slack > 0 means shrinking that service by less than the slack does not
move the current end-to-end estimate.

Existing fan-out is already concurrent. Opportunities are only YAML
what-ifs the author declared.

YAML is reviewable and CI-friendly. Determinism makes diffs explainable.
Traces are out of scope: this tool analyzes declared architecture, not
telemetry. Longest path is used because it matches deterministic
dependency start times (`max` of parents).
