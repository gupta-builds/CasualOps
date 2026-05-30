import type { ExecutionEvent, RunResponse } from "./hivemind-types";
import { parseRunResponse, SchemaValidationError } from "./hivemind-schema";

const DEFAULT_ENDPOINT = "http://localhost:8000/run";
const STORAGE_KEY = "hivemind:apiUrl";
/** Full LangGraph runs (orchestrator + parents + children + causal) often exceed 60s. */
const RUN_REQUEST_TIMEOUT_MS = 600_000;

function normalizeBase(url: string): string {
  const trimmed = url.trim().replace(/\/+$/, "");
  if (!trimmed) return DEFAULT_ENDPOINT;
  if (trimmed === "/run") return "http://localhost:8000/run";
  // If user pasted a base URL (no /run), append it.
  if (/\/run$/i.test(trimmed)) return trimmed;
  return `${trimmed}/run`;
}

export function getApiUrl(): string {
  if (typeof window === "undefined") return DEFAULT_ENDPOINT;
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored && stored.trim()) return normalizeBase(stored);
  } catch {
    /* ignore */
  }
  return DEFAULT_ENDPOINT;
}

/** API origin without the `/run` suffix (for SSE and health). */
export function getApiBase(): string {
  return getApiUrl().replace(/\/run\/?$/i, "");
}

export function setApiUrl(url: string): string {
  const next = url.trim();
  if (typeof window !== "undefined") {
    try {
      if (!next) window.localStorage.removeItem(STORAGE_KEY);
      else window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* ignore */
    }
  }
  return getApiUrl();
}

export function clearApiUrl(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

export const DEFAULT_API_URL = DEFAULT_ENDPOINT;

export function newRunId(): string {
  const stamp = new Date().toISOString().replace(/[-:]/g, "").slice(0, 15);
  const suffix =
    typeof crypto !== "undefined" && crypto.randomUUID
      ? crypto.randomUUID().slice(0, 8)
      : Math.random().toString(36).slice(2, 10);
  return `run-${stamp}-${suffix}`;
}

export function streamRunEvents(
  runId: string,
  onEvent: (event: ExecutionEvent) => void,
  signal?: AbortSignal,
  onError?: (message: string) => void,
): () => void {
  const url = `${getApiBase()}/run/${encodeURIComponent(runId)}/events`;
  const source = new EventSource(url);
  let reportedError = false;

  const onMessage = (message: MessageEvent<string>) => {
    try {
      const parsed = JSON.parse(message.data) as ExecutionEvent;
      onEvent(parsed);
    } catch {
      /* ignore malformed SSE payloads */
    }
  };

  const onStreamError = () => {
    if (reportedError || source.readyState === EventSource.CLOSED) return;
    reportedError = true;
    onError?.(
      "Lost connection to execution stream. Check that the API is running and KAFKA_BOOTSTRAP is set.",
    );
  };

  source.addEventListener("message", onMessage as EventListener);
  source.onerror = onStreamError;

  const abort = () => {
    source.removeEventListener("message", onMessage as EventListener);
    source.onerror = null;
    source.close();
  };

  signal?.addEventListener("abort", abort, { once: true });

  return abort;
}

export async function runCausalEngine(
  taskDescription: string,
  options?: { runId?: string },
): Promise<RunResponse> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), RUN_REQUEST_TIMEOUT_MS);
  const endpoint = getApiUrl();
  const runId = options?.runId;

  try {
    const res = await fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        // Skip the localtunnel.me browser warning interstitial.
        "Bypass-Tunnel-Reminder": "true",
      },
      body: JSON.stringify({
        task_description: taskDescription,
        ...(runId ? { run_id: runId } : {}),
      }),
      signal: controller.signal,
    });

    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(
        `Backend returned ${res.status} ${res.statusText}${text ? `: ${text.slice(0, 200)}` : ""}`,
      );
    }

    const json = await res.json();
    return parseRunResponse(json);
  } catch (err) {
    if (err instanceof SchemaValidationError) {
      throw err;
    }
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new Error(
        `Request timed out after ${Math.round(RUN_REQUEST_TIMEOUT_MS / 60_000)} minutes.`,
      );
    }
    if (err instanceof TypeError) {
      throw new Error(
        `Could not reach the HiveMind backend at ${endpoint}. Check the internal /run route or configure a reachable external endpoint in Settings.`,
      );
    }
    throw err;
  } finally {
    clearTimeout(timeout);
  }
}
