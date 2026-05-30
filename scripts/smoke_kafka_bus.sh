#!/usr/bin/env bash
# Manual acceptance gate for the Kafka event bus (Phase 1).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

API_URL="${API_URL:-http://localhost:8000}"
COMPOSE="${COMPOSE:-docker compose}"

echo "==> Bus serde tests"
PYTHONPATH=src python3 -m pytest tests/test_bus_serde.py tests/test_bus_summary.py tests/test_bus_kafka_off.py tests/test_coordinator_store.py tests/test_coordinator_refutation.py tests/test_coordinator_runner.py tests/test_worker_dispatch.py tests/test_api_async_run.py -q

echo "==> API health"
curl -sf "${API_URL}/health" | grep -q '"status":"ok"'

if ${COMPOSE} ps --status running 2>/dev/null | grep -q redpanda; then
  echo "==> Redpanda topics (expect hivemind.* after at least one run)"
  ${COMPOSE} exec -T redpanda rpk topic list
else
  echo "==> Skipping Redpanda topic check (redpanda container not running)"
fi

echo "==> Smoke checks passed"
