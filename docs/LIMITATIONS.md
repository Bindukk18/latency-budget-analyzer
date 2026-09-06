# Limitations

- deterministic architecture-budget analyzer
- supplied latencies may not match production
- per-service p95 values do not compose into exact end-to-end p95
- no queueing model
- no network jitter
- no correlated failures
- no retry-amplification model
- no throughput/capacity analysis
- no tracing ingestion
- no stochastic distributions
- parallelization safety must be declared
- critical path can change under real traffic
- not a production APM replacement
- no production performance claim
