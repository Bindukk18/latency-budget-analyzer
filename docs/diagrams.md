# Example graphs

## Sequential (`examples/sequential.yaml`)

Critical path is the entire chain (275 ms).

```mermaid
flowchart LR
    gateway --> checkout --> pricing --> inventory --> payment --> response
```

## Parallel (`examples/parallel.yaml`)

Critical path highlighted: gateway → aggregator → recommendations → response (170 ms).

```mermaid
flowchart LR
    gateway --> aggregator
    aggregator --> profile --> response
    aggregator --> catalog --> response
    aggregator --> recommendations --> response
    style gateway fill:#f6d55c
    style aggregator fill:#f6d55c
    style recommendations fill:#f6d55c
    style response fill:#f6d55c
```
