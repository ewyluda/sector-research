"use client";
import type { SensitivityGrid } from "@/lib/api";
import { heatmapColor } from "./heatmapColors";

export function SensitivityHeatmap({ grid, currentPrice }: { grid: SensitivityGrid; currentPrice: number }) {
  const flat = grid.values.flat();
  const min = Math.min(...flat);
  const max = Math.max(...flat);
  const range = Math.max(currentPrice - min, max - currentPrice);
  return (
    <div className="text-xs">
      <div className="mb-1 text-slate-400">{grid.x_dim} &times; {grid.y_dim}</div>
      <table className="border-collapse">
        <thead>
          <tr>
            <th></th>
            {grid.x_values.map((v, i) =>
              i % 4 === 0 ? (
                <th key={i} className="text-center text-slate-500 px-0.5">{v.toFixed(2)}</th>
              ) : (
                <th key={i}></th>
              )
            )}
          </tr>
        </thead>
        <tbody>
          {grid.values.map((row, ri) => (
            <tr key={ri}>
              <td className="text-right text-slate-500 pr-1">
                {ri % 4 === 0 ? grid.y_values[ri].toFixed(2) : ""}
              </td>
              {row.map((v, ci) => (
                <td
                  key={ci}
                  title={`x=${grid.x_values[ci].toFixed(3)}, y=${grid.y_values[ri].toFixed(3)} → ${v.toFixed(2)}`}
                  style={{ backgroundColor: heatmapColor(v, currentPrice, range) }}
                  className="w-3 h-3 p-0"
                />
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
