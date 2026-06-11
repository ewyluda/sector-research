/**
 * buildCategoryWrappers — pure (no React) helper that converts a
 * `Record<string, CategoryState>` into the `Record<string, CategoryOutput | null>`
 * shape DeepDiveDashboard expects, while keeping wrapper objects referentially
 * stable across calls when the underlying CategoryState reference is unchanged.
 *
 * The caller is responsible for threading in a persistent cache object (a Map)
 * so this function remains React-free and fully unit-testable.
 *
 * Cache shape: Map<categoryName, [CategoryState source, CategoryOutput | null wrapper]>
 * On each call:
 *   - If categories[k] is reference-equal to cache.get(k)[0], reuse cache.get(k)[1].
 *   - Otherwise, build a new wrapper, cache it, and return it.
 * Keys absent from `categories` are removed from the cache.
 */

import type { CategoryOutput, DeepDiveCategoryStructured } from "./api.ts";

export interface CategoryState {
  status: "pending" | "running" | "pass" | "fail";
  score: number | null;
  key_findings: string[];
  structured: DeepDiveCategoryStructured | null;
}

export type WrapperCache = Map<string, [CategoryState, CategoryOutput | null]>;

export function buildCategoryWrappers(
  categories: Record<string, CategoryState>,
  cache: WrapperCache,
): Record<string, CategoryOutput | null> {
  const result: Record<string, CategoryOutput | null> = {};

  for (const [k, v] of Object.entries(categories)) {
    const cached = cache.get(k);
    if (cached !== undefined && cached[0] === v) {
      // CategoryState reference unchanged — reuse existing wrapper
      result[k] = cached[1];
    } else {
      // Build a new wrapper for this category
      const wrapper: CategoryOutput | null =
        v.status === "fail"
          ? null
          : {
              score: v.score ?? 0,
              content: "",
              key_findings: v.key_findings,
              citations: [],
              structured: v.structured ?? undefined,
            };
      cache.set(k, [v, wrapper]);
      result[k] = wrapper;
    }
  }

  // Evict stale keys that are no longer in `categories`
  for (const k of cache.keys()) {
    if (!(k in categories)) {
      cache.delete(k);
    }
  }

  return result;
}
