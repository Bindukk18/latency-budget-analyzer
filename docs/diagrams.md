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
    style gateway fill:#c5d8f0,stroke:#2c5f8a,color:#1a1a1a
    style aggregator fill:#c5d8f0,stroke:#2c5f8a,color:#1a1a1a
    style recommendations fill:#c5d8f0,stroke:#2c5f8a,color:#1a1a1a
    style response fill:#c5d8f0,stroke:#2c5f8a,color:#1a1a1a
```
