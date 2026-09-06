# Input schema

```yaml
name: checkout-api
target_p95_ms: 300
services:
  gateway:
    latency_ms: 15
    depends_on: []
    criticality: required   # optional
    owner: platform         # optional
parallelization_candidates:  # optional, explicit only
  - name: pricing-inventory
    services: [pricing, inventory]
    common_dependency: checkout
```

`latency_ms` is a **planning** value: allocated budget, observed
representative p95, or another chosen number. The analyzer does not infer
statistical meaning.

`parallelizable_with` is **rejected**. Topology cannot prove two services
are safe to overlap; declare `parallelization_candidates` instead.

A candidate means the listed services may start after `common_dependency`
for WHAT-IF analysis. The rewrite drops only edges among those services.
Unrelated dependencies are kept. Each listed service must already be
downstream of `common_dependency`.

`criticality: optional` is reported. The node stays in the request-path
analysis.
