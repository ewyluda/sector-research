// Diverging palette around iso-value (current price). Greens above, reds below.
export function heatmapColor(value: number, ref: number, range: number): string {
  const norm = Math.max(-1, Math.min(1, (value - ref) / Math.max(range, 1e-9)));
  if (norm >= 0) {
    const t = norm;
    return `rgb(${Math.round(40 + t * 40)}, ${Math.round(150 - t * 40)}, ${Math.round(80 - t * 30)})`; // greens
  }
  const t = -norm;
  return `rgb(${Math.round(150 + t * 60)}, ${Math.round(60 + t * 30)}, ${Math.round(60 + t * 30)})`; // reds
}
