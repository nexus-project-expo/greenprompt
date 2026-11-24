export type Receipt = {
  tier: string;
  wh: number;
  wh_low: number;
  wh_high: number;
  g_co2: number;
  ml_water: number;
  baseline_wh: number;
  saved_wh: number;
  saved_pct: number;
  measured: boolean;
  sources: string[];
  latency_s: number;
  model: string;
  escalated: boolean;
  grid_note: string;
  idle_w: number | null;
  power_trace: [number, number][];
};

export type ChatResult = {
  answer: string;
  receipt: Receipt;
  route: { tier: string; p_hard: number; reasons: string[] } | null;
  cache: {
    hit: boolean; cacheable: boolean; cache_reason: string; similarity?: number; matched_prompt?: string;
    nearest?: { prompt: string; similarity: number; why: string };
  };
  error: string | null;
};

export type Status = {
  warm: string;
  local_model: string | null;
  local_name: string | null;
  cloud: string;
  large_name: string;
  grid: string | null;
  grid_g_per_kwh: number;
  idle_w: number | null;
  gpu_busy: boolean;
};

export type Stats = {
  requests: number;
  cache_hit_rate: number;
  small_share: number;
  tiers: Record<string, number>;
  wh: number;
  baseline_wh: number;
  saved_wh: number;
  saved_pct: number;
  g_co2: number;
  g_co2_saved: number;
  ml_water: number;
  measured: number;
  median_latency_s: Record<string, number | null>;
  cumulative: { ts: number; wh: number; baseline_wh: number }[];
};

type Failure = { error: string };

/** Fetch JSON from the local server. Never throws: network trouble comes back as {error}. */
export async function api<T>(path: string, body?: unknown, timeoutMs = 10000): Promise<T | Failure> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(path, {
      method: body === undefined ? "GET" : "POST",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: ctrl.signal,
    });
    return (await res.json()) as T | Failure;
  } catch {
    return { error: ctrl.signal.aborted ? "timeout" : "server_unreachable" };
  } finally {
    clearTimeout(timer);
  }
}

export const isError = (x: unknown): x is Failure =>
  typeof x === "object" && x !== null && typeof (x as Failure).error === "string" && !("answer" in x);

/** Wh to 3 significant figures, without scientific notation. */
export function sig(x: number, digits = 3): string {
  if (x === 0) return "0";
  if (Math.abs(x) < 1e-5) return x > 0 ? "<0.00001" : "-<0.00001";
  return String(Number(x.toPrecision(digits)));
}

export const pct = (x: number) => `${Math.round(x)}%`;

export const ERRORS: Record<string, string> = {
  no_model: "No model could answer. Cached answers still work. Check the internet or Ollama.",
  internal: "Something went wrong on the server. Try again.",
  server_unreachable: "Can't reach the GreenPrompt server. Is uvicorn running?",
  timeout: "The request took too long and was stopped. Try again.",
  empty_prompt: "Type a question first.",
};
