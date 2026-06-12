"use client";

/**
 * SVG force-graph renderer. Layout is computed synchronously (d3-force
 * ticked to convergence in a useMemo) — no live physics, which avoids
 * per-tick React re-renders. Interactions: d3-zoom pan/zoom on the svg
 * root (the only d3-selection use), pointer-drag to reposition a node,
 * click to select.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from "d3-force";
import { select } from "d3-selection";
import { zoom, zoomIdentity, type ZoomTransform } from "d3-zoom";
import { edgeColor, edgeWidth, type SimLink, type SimNode } from "@/lib/themeGraph";

type LayoutNode = SimNode & SimulationNodeDatum;
type LayoutLink = Omit<SimLink, "source" | "target"> &
  SimulationLinkDatum<LayoutNode>;

interface Props {
  nodes: SimNode[];
  links: SimLink[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}

const WIDTH = 960;
const HEIGHT = 640;

export default function ForceGraphCanvas({
  nodes, links, selectedId, onSelect,
}: Props) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [transform, setTransform] = useState<ZoomTransform>(zoomIdentity);
  // Manual drag overrides, keyed by node id.
  const [overrides, setOverrides] = useState<Map<string, { x: number; y: number }>>(
    new Map(),
  );
  const dragRef = useRef<{ id: string; moved: boolean } | null>(null);

  const layout = useMemo(() => {
    // d3-force mutates node/link objects — work on copies.
    const simNodes: LayoutNode[] = nodes.map((n) => ({ ...n }));
    const simLinks: LayoutLink[] = links.map((l) => ({ ...l }));
    const sim = forceSimulation(simNodes)
      .force(
        "link",
        forceLink<LayoutNode, LayoutLink>(simLinks)
          .id((d) => d.id)
          .distance(70),
      )
      .force("charge", forceManyBody().strength(-180))
      .force("center", forceCenter(0, 0))
      .force("collide", forceCollide<LayoutNode>().radius((d) => d.radius + 6))
      .stop();
    sim.tick(300);
    return { simNodes, simLinks };
  }, [nodes, links]);

  useEffect(() => {
    if (!svgRef.current) return;
    const behavior = zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.2, 6])
      .filter((event) => !(event.type === "mousedown" && dragRef.current))
      .on("zoom", (event) => setTransform(event.transform));
    const sel = select(svgRef.current);
    sel.call(behavior);
    return () => {
      sel.on(".zoom", null);
    };
  }, []);

  const pos = (n: LayoutNode) =>
    overrides.get(n.id) ?? { x: n.x ?? 0, y: n.y ?? 0 };

  const toGraphCoords = (clientX: number, clientY: number) => {
    const rect = svgRef.current!.getBoundingClientRect();
    const sx = ((clientX - rect.left) / rect.width) * WIDTH - WIDTH / 2;
    const sy = ((clientY - rect.top) / rect.height) * HEIGHT - HEIGHT / 2;
    return {
      x: (sx - transform.x) / transform.k,
      y: (sy - transform.y) / transform.k,
    };
  };

  return (
    <svg
      ref={svgRef}
      viewBox={`${-WIDTH / 2} ${-HEIGHT / 2} ${WIDTH} ${HEIGHT}`}
      className="w-full rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)]"
      style={{ height: "640px", cursor: "grab" }}
      onPointerMove={(e) => {
        const drag = dragRef.current;
        if (!drag) return;
        drag.moved = true;
        const { x, y } = toGraphCoords(e.clientX, e.clientY);
        setOverrides((prev) => new Map(prev).set(drag.id, { x, y }));
      }}
      onPointerUp={() => {
        const drag = dragRef.current;
        dragRef.current = null;
        if (drag && !drag.moved) {
          onSelect(selectedId === drag.id ? null : drag.id);
        }
      }}
      onClick={(e) => {
        // Background click clears selection (node clicks stopPropagation).
        if (e.target === svgRef.current) onSelect(null);
      }}
    >
      <g transform={transform.toString()}>
        {layout.simLinks.map((l, i) => {
          // After forceLink(...).id(...) + tick(), d3 has replaced the string
          // source/target with node object references — the cast is sound.
          const s = l.source as LayoutNode;
          const t = l.target as LayoutNode;
          const sp = pos(s);
          const tp = pos(t);
          const w = edgeWidth(l.magnitudePct);
          return (
            <g key={`${s.id}|${t.id}|${l.type}|${i}`}>
              <line
                x1={sp.x} y1={sp.y} x2={tp.x} y2={tp.y}
                stroke={edgeColor(l.type)}
                strokeWidth={l.bilateral ? w + 2 : w}
                strokeOpacity={0.55}
              />
              {l.bilateral && (
                <line
                  x1={sp.x} y1={sp.y} x2={tp.x} y2={tp.y}
                  stroke="var(--color-bg)"
                  strokeWidth={Math.max(0.75, w - 1)}
                  strokeOpacity={1}
                />
              )}
            </g>
          );
        })}
        {layout.simNodes.map((n) => {
          const p = pos(n);
          const selected = n.id === selectedId;
          return (
            <g
              key={n.id}
              transform={`translate(${p.x},${p.y})`}
              style={{ cursor: "pointer" }}
              onPointerDown={(e) => {
                e.stopPropagation();
                dragRef.current = { id: n.id, moved: false };
              }}
              onClick={(e) => e.stopPropagation()}
            >
              <circle
                r={n.radius}
                fill={n.isSeed ? "var(--color-accent)" : "var(--color-surface)"}
                stroke={selected ? "#fff" : "var(--color-border)"}
                strokeWidth={selected ? 2.5 : 1.25}
                opacity={n.isUnresolved ? 0.55 : 1}
              />
              <text
                y={n.radius + 11}
                textAnchor="middle"
                className="select-none"
                fill="var(--color-text-primary)"
                fontSize={10}
                opacity={n.isUnresolved ? 0.6 : 0.9}
              >
                {n.label}
              </text>
            </g>
          );
        })}
      </g>
    </svg>
  );
}
