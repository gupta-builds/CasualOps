import type { ExecutionEvent } from "./hivemind-types";
import type { RunResponse } from "./hivemind-types";
import { newRunId, runCausalEngine, streamRunEvents } from "./hivemind-api";

function uid() {
  return `e_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;
}

/**
 * Runs the causal engine with live SSE telemetry from the HiveMind API.
 * Client supplies run_id, opens EventSource, then POST /run with the same id.
 */
export async function executeWithProgress(
  taskDescription: string,
  onEvent: (event: ExecutionEvent) => void,
): Promise<RunResponse> {
  const runId = newRunId();
  const controller = new AbortController();
  const stopStream = streamRunEvents(runId, onEvent, controller.signal);

  try {
    return await runCausalEngine(taskDescription, { runId });
  } catch (err) {
    onEvent({
      id: uid(),
      phase: "ERROR",
      message: err instanceof Error ? err.message : "Execution failed",
      status: "error",
      ts: Date.now(),
    });
    throw err;
  } finally {
    controller.abort();
    stopStream();
  }
}
