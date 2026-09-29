/**
 * Core fetch plumbing and shared primitive types.
 * All other api/* modules import `apiFetch` and `BASE` from here.
 */

/** Read-only demo build: answers from recorded responses (see demo.ts). */
export const DEMO = process.env.NEXT_PUBLIC_DEMO === "1";

export const BASE = DEMO ? "" : (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000");

/** fetch, or the recorded-response responder in a demo build. Use this
 *  rather than fetch() so every call works in both. */
export async function request(url: string, init?: RequestInit): Promise<Response> {
  if (DEMO) {
    const { demoFetch } = await import("./demo");
    return demoFetch(url, init);
  }
  return fetch(url, init);
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await request(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${text}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ── Shared primitive type used across multiple modules ────────────────────────

export interface Citation {
  metric: string;
  source_name: string;
  source_url: string;
  tier: 1 | 2;
  value: string;
}
