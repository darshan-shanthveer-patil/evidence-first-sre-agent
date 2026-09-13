# Evidence-first SRE agent

An experimental, read-only incident investigation agent for Kubernetes
workloads. It turns observations from operational systems into ranked,
auditable hypotheses without presenting guesses as facts.

The first milestone is intentionally deterministic. It establishes the
evidence contract and safety boundaries before an LLM is introduced.

## Status

Early development. The current CLI analyzes captured incident evidence. Live
Kubernetes and Prometheus collectors are planned next.

