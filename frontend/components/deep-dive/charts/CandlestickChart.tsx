"use client";

import { useEffect, useRef } from "react";
import {
  createChart,
  ColorType,
  CrosshairMode,
  LineStyle,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  type IChartApi,
} from "lightweight-charts";
import type { DailyPrice } from "@/lib/api";

interface CandlestickChartProps {
  data: DailyPrice[];
  height?: number;
}

const SMA_CONFIG = [
  { key: "sma_9" as const, color: "#94a3b8", width: 1 as const, title: "SMA 9" },
  { key: "sma_20" as const, color: "#facc15", width: 1 as const, title: "SMA 20" },
  { key: "sma_50" as const, color: "#60a5fa", width: 2 as const, title: "SMA 50" },
  { key: "sma_100" as const, color: "#a78bfa", width: 2 as const, title: "SMA 100" },
  { key: "sma_200" as const, color: "#f97316", width: 2 as const, title: "SMA 200" },
];

export function CandlestickChart({ data, height = 450 }: CandlestickChartProps) {
  const mainRef = useRef<HTMLDivElement>(null);
  const rsiRef = useRef<HTMLDivElement>(null);
  const mainChartRef = useRef<IChartApi | null>(null);
  const rsiChartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!mainRef.current || !rsiRef.current || data.length === 0) return;

    const mainHeight = Math.round(height * 0.7);
    const rsiHeight = Math.round(height * 0.3);

    // Read CSS variables from the DOM
    const styles = getComputedStyle(document.documentElement);
    const bgColor = styles.getPropertyValue("--color-surface").trim() || "#1a1a2e";
    const borderColor = styles.getPropertyValue("--color-border").trim() || "#2a2a3e";
    const textColor = styles.getPropertyValue("--color-text-muted").trim() || "#888";

    // ── Main chart: candlestick + volume + SMAs ─────────────────────────
    const mainChart = createChart(mainRef.current, {
      height: mainHeight,
      layout: { background: { type: ColorType.Solid, color: bgColor }, textColor },
      grid: { vertLines: { color: borderColor }, horzLines: { color: borderColor } },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor },
      timeScale: { borderColor, timeVisible: false },
    });

    // Candlestick series
    const candleSeries = mainChart.addSeries(CandlestickSeries, {
      upColor: "#34d399",
      downColor: "#f87171",
      borderUpColor: "#34d399",
      borderDownColor: "#f87171",
      wickUpColor: "#34d399",
      wickDownColor: "#f87171",
    });
    candleSeries.setData(
      data.map((d) => ({ time: d.date, open: d.open, high: d.high, low: d.low, close: d.close }))
    );

    // Volume histogram
    const volumeSeries = mainChart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });
    mainChart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });
    volumeSeries.setData(
      data.map((d) => ({
        time: d.date,
        value: d.volume,
        color: d.close >= d.open ? "rgba(52, 211, 153, 0.3)" : "rgba(248, 113, 113, 0.3)",
      }))
    );

    // SMA line series
    for (const sma of SMA_CONFIG) {
      const series = mainChart.addSeries(LineSeries, {
        color: sma.color,
        lineWidth: sma.width,
        title: sma.title,
        priceLineVisible: false,
        lastValueVisible: false,
      });
      series.setData(
        data
          .filter((d) => d[sma.key] != null)
          .map((d) => ({ time: d.date, value: d[sma.key]! }))
      );
    }

    // ── RSI chart ───────────────────────────────────────────────────────
    const rsiChart = createChart(rsiRef.current, {
      height: rsiHeight,
      layout: { background: { type: ColorType.Solid, color: bgColor }, textColor },
      grid: { vertLines: { color: borderColor }, horzLines: { color: borderColor } },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor },
      timeScale: { borderColor, timeVisible: false },
    });

    const rsiSeries = rsiChart.addSeries(LineSeries, {
      color: "#60a5fa",
      lineWidth: 2,
      title: "RSI(14)",
      priceLineVisible: false,
      lastValueVisible: true,
    });
    rsiSeries.setData(
      data
        .filter((d) => d.rsi != null)
        .map((d) => ({ time: d.date, value: d.rsi! }))
    );

    // RSI reference lines at 70 and 30
    rsiSeries.createPriceLine({
      price: 70,
      color: "#f87171",
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      axisLabelVisible: true,
      title: "",
    });
    rsiSeries.createPriceLine({
      price: 30,
      color: "#34d399",
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      axisLabelVisible: true,
      title: "",
    });

    // Sync time scales
    mainChart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
      if (range) rsiChart.timeScale().setVisibleLogicalRange(range);
    });
    rsiChart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
      if (range) mainChart.timeScale().setVisibleLogicalRange(range);
    });

    // Fit content
    mainChart.timeScale().fitContent();
    rsiChart.timeScale().fitContent();

    mainChartRef.current = mainChart;
    rsiChartRef.current = rsiChart;

    // Resize observer
    const observer = new ResizeObserver(() => {
      if (mainRef.current) mainChart.applyOptions({ width: mainRef.current.clientWidth });
      if (rsiRef.current) rsiChart.applyOptions({ width: rsiRef.current.clientWidth });
    });
    if (mainRef.current) observer.observe(mainRef.current);

    return () => {
      observer.disconnect();
      mainChart.remove();
      rsiChart.remove();
      mainChartRef.current = null;
      rsiChartRef.current = null;
    };
  }, [data, height]);

  if (data.length === 0) return null;

  return (
    <div>
      <div ref={mainRef} />
      <div ref={rsiRef} />
      {/* SMA Legend */}
      <div className="flex flex-wrap gap-3 mt-2">
        {SMA_CONFIG.map((sma) => (
          <div key={sma.key} className="flex items-center gap-1">
            <span className="w-3 h-0.5 rounded" style={{ backgroundColor: sma.color }} />
            <span className="text-[9px] text-[var(--color-text-muted)]">{sma.title}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
