"use client";
import { useState } from "react";

export function WhatIfScratchPanel({ baseline }: { baseline: { growth: number; margin: number; multiple: number } }) {
  const [growth, setGrowth] = useState(baseline.growth);
  const [margin, setMargin] = useState(baseline.margin);
  const [multiple, setMultiple] = useState(baseline.multiple);
  return (
    <section className="border border-slate-800 rounded p-4">
      <h3 className="text-sm font-semibold text-slate-300 mb-2">What-if scratch</h3>
      <p className="text-xs text-slate-500 mb-3">
        Move the sliders; nothing is saved. Re-evaluation is illustrative only — for full recompute, edit drivers in the
        Forecast tab.
      </p>
      <div className="space-y-2">
        <label className="block text-xs">
          Revenue growth: {(growth * 100).toFixed(1)}%
          <input
            type="range"
            min={-5}
            max={30}
            step={0.1}
            value={growth * 100}
            onChange={(e) => setGrowth(Number(e.target.value) / 100)}
            className="w-full"
          />
        </label>
        <label className="block text-xs">
          Gross margin: {(margin * 100).toFixed(1)}%
          <input
            type="range"
            min={-50}
            max={80}
            step={0.5}
            value={margin * 100}
            onChange={(e) => setMargin(Number(e.target.value) / 100)}
            className="w-full"
          />
        </label>
        <label className="block text-xs">
          Terminal multiple: {multiple.toFixed(1)}x
          <input
            type="range"
            min={1}
            max={40}
            step={0.5}
            value={multiple}
            onChange={(e) => setMultiple(Number(e.target.value))}
            className="w-full"
          />
        </label>
      </div>
    </section>
  );
}
