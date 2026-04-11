/**
 * Page 2 — Theme Detail (/theme/[id])
 * Two-panel layout:
 *   Left:  Sortable/filterable company list with signal cards
 *   Right: Expanded company view (rendered client-side on selection)
 */

import { themes, discovery } from "@/lib/api";
import ThemeDetailClient from "./ThemeDetailClient";

export const dynamic = "force-dynamic";

interface Props {
  params: Promise<{ id: string }>;
}

export default async function ThemeDetailPage({ params }: Props) {
  const { id } = await params;

  const [theme, discoverData] = await Promise.all([
    themes.get(id).catch(() => null),
    discovery.run(id).catch(() => null),
  ]);

  if (!theme) {
    return (
      <div className="py-16 text-center text-[var(--text-muted)] text-sm">
        Theme not found.
      </div>
    );
  }

  return (
    <ThemeDetailClient
      theme={theme}
      initialData={discoverData}
    />
  );
}
