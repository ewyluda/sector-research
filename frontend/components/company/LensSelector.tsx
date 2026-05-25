"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { themes } from "@/lib/api";
import type { Theme } from "@/lib/api";

export function LensSelector() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const lens = params.get("lens") ?? "";
  const [themeList, setThemeList] = useState<Theme[]>([]);

  useEffect(() => {
    themes.list().then(setThemeList).catch(() => setThemeList([]));
  }, []);

  function onChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const next = new URLSearchParams(Array.from(params.entries()));
    if (e.target.value) next.set("lens", e.target.value);
    else next.delete("lens");
    const qs = next.toString();
    router.push(qs ? `${pathname}?${qs}` : pathname);
  }

  return (
    <label className="flex items-center gap-1.5 text-xs text-[var(--text-muted)]">
      Lens:
      <select
        value={lens}
        onChange={onChange}
        className="rounded-md border border-[var(--border)] bg-[var(--surface-alt)] px-2 py-1 text-xs text-[var(--text)]"
      >
        <option value="">All</option>
        {themeList.map((t) => (
          <option key={t.id} value={t.id}>
            {t.name}
          </option>
        ))}
      </select>
    </label>
  );
}
