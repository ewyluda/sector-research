"use client";

import { useEffect, useRef, useState } from "react";

const STORAGE_PREFIX = "sr:collapse:";

/**
 * Persist a section's collapse state under a stable id. Reads the initial
 * value from localStorage on mount (SSR-safe: first render matches the server
 * default) and writes updates back. Keyed per section id, so every section's
 * toggle survives navigation and reloads.
 *
 * The `hydrated` ref gates writes so the first render — which uses the
 * default, not the persisted value — doesn't clobber localStorage before the
 * read effect has a chance to reconcile.
 */
export function usePersistedCollapse(id: string, defaultCollapsed = false): [boolean, (next: boolean | ((prev: boolean) => boolean)) => void] {
  const [collapsed, setCollapsed] = useState(defaultCollapsed);
  const isFirstWrite = useRef(true);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(STORAGE_PREFIX + id);
      // Sync-set is intentional: we deliberately defer localStorage reads until
      // after hydration so SSR and first client render agree on `defaultCollapsed`.
      // Doing this through useSyncExternalStore would require custom subscription
      // plumbing (storage events don't fire in the originating tab) for no gain.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      if (raw === "1") setCollapsed(true);
      else if (raw === "0") setCollapsed(false);
    } catch {
      // localStorage may be unavailable (private mode, SSR fallbacks)
    }
  }, [id]);

  useEffect(() => {
    // Skip the first write — it runs with the default value on mount, before
    // the read effect has had a chance to reconcile with localStorage.
    // Writing here would clobber any persisted value.
    if (isFirstWrite.current) {
      isFirstWrite.current = false;
      return;
    }
    try {
      window.localStorage.setItem(STORAGE_PREFIX + id, collapsed ? "1" : "0");
    } catch {
      // ignore write failures
    }
  }, [id, collapsed]);

  return [collapsed, setCollapsed];
}
