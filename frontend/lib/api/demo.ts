/**
 * Read-only demo mode (NEXT_PUBLIC_DEMO=1 at build time): API requests are
 * answered from responses recorded against a real backend (demo/api.json,
 * recorded by demo/record.mjs) instead of the network. Writes are refused.
 * Only loaded in demo builds — see `request` in core.ts.
 */
type Recorded = Record<string, { status: number; body: string }>;

let store: Promise<Recorded> | null = null;
let undated: Map<string, string> | null = null;

// Some requests carry today's date (the calendar's start/end). Recorded on one
// day, they'd miss on the next — so fall back to the recorded request that
// matches once ISO dates are masked.
const mask = (key: string) => key.replace(/\d{4}-\d{2}-\d{2}/g, "<date>");

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

export async function demoFetch(url: string, init?: RequestInit): Promise<Response> {
  const method = (init?.method ?? "GET").toUpperCase();
  if (method !== "GET") return json(403, { detail: "This is a read-only demo — changes are disabled." });
  store ??= import("@/demo/api.json").then((m) => m.default as Recorded);
  const recorded = await store;
  undated ??= new Map(Object.keys(recorded).map((k) => [mask(k), k]));
  const key = `GET ${url}`;
  const hit = recorded[key] ?? recorded[undated.get(mask(key)) ?? ""];
  if (!hit) return json(404, { detail: "Not part of the recorded demo." });
  return new Response(hit.body, { status: hit.status, headers: { "Content-Type": "application/json" } });
}
