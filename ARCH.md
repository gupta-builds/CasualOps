# HiveMind architecture decisions

Record of major design choices for the Kafka event bus (Phase 0–1). Short justifications for later review.

## Event bus

| Decision | Choice | Justification |
|----------|--------|---------------|
| Broker | Redpanda (Kafka API) | Single container, Kafka-compatible, low local ops overhead |
| Client library | `aiokafka` | Matches async FastAPI / `run_hivemind`; non-blocking producer lifecycle |
| Partition key | `run_id` | Per-run ordering; all artifacts for one investigation co-locate |
| Per-agent ordering | `sequence` in envelope | Monotonic per `(run_id, agent_id)` without composite Kafka keys |
| Serialization | JSON UTF-8 (v1) | Simple debugging with `rpk topic consume`; Schema Registry deferred to Phase 2 |
| Bus optional | No-op when `KAFKA_BOOTSTRAP` unset | Local dev without Docker; tests without broker |
| Client `/run` timeout | 10 minutes | Full agent graph commonly takes 2–3+ minutes; old 60s abort fired before backend finished |
| Kafka publish thread | Dedicated worker loop | Sync LangGraph nodes were blocking on FastAPI loop → 30s publish timeouts |
| Publish context in workers | `bind_from_state()` per node | `ContextVar` does not propagate to LangGraph thread-pool workers; `run_id` is on `GraphState` / fan-out payloads |
| Evidence on bus | Not in Phase 1 | Dataset rows stay API/compiler-only; avoids LLM row leakage on the bus |

## Topics

| Topic | Purpose |
|-------|---------|
| `hivemind.runs` | `run_started`, `run_completed`, `run_failed` |
| `hivemind.spawn` | `AgentConfig`, `ChildConfig` |
| `hivemind.artifacts` | memos, rankings, causal payloads, estimate reports |
| `hivemind.telemetry` | UI `ExecutionEvent`-compatible phase events |
| `hivemind.evidence` | Reserved; API-only for now |

## API and UI

| Decision | Choice | Justification |
|----------|--------|---------------|
| `/run` semantics | Blocking JSON unchanged | No Phase 2 async enqueue yet |
| `run_id` | Client-supplied (optional) | Enables SSE subscription before POST without 202/poll |
| SSE route | `GET /run/{run_id}/events` | Standard EventSource; maps telemetry envelopes to `ExecutionEvent` |
| SSE offset | `auto_offset_reset=latest` | Client connects before POST; only in-flight run events needed |
| LangGraph state | Full memos in state (Phase 1) | Preserves `operator.add` reducers; slimming optional later |
| UI phases | Graph-aligned (`ORCHESTRATOR`, …) | Replaces fake `TOKENIZE`/`HYPOTHESIS` simulator phases |

## Delivery

| Decision | Choice | Justification |
|----------|--------|---------------|
| Branch policy | `feature/kafka-bus` → single merge to `main` | Owner policy: no partial merges until end-to-end works |
| `data/*.json` | Still written at run end | User-facing bundle; Kafka is event log not query API |

## Phase 1b (bus summaries)

| Decision | Choice | Justification |
|----------|--------|---------------|
| GraphState slimming | Deferred | Evaluator/causal still need full memos in-process until Phase 2 workers |
| `bus_summary` | Counters on publish context | Bridges Kafka event log and `data/*.json` tier metrics without consuming topics |
| Benchmarking | Counts from summary + sample memo | Orchestrator/parent/child/evaluator tiers use bus counts; causal/estimator unchanged |

`bus_summary` fields: `parent_config_count`, `child_config_count`, `memo_count`, `has_ranked_strategies`, `has_causal_payload`, `has_estimate_report`.

## Deferred (Phase 2+)

- Distributed workers consuming `hivemind.spawn`
- Idempotency keys, DLQ, Avro schemas
- `hivemind.evidence` topic
- Slim `GraphState` (refs only) and benchmarking from counts
- S3/MinIO for large payloads
