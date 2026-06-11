/**
 * Core fetch plumbing and shared primitive types.
 * All other api/* modules import `apiFetch` and `BASE` from here.
 */

export const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
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
