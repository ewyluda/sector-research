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
import { zoom, zoomIdentity, type ZoomBehavior, type ZoomTransform } from "d3-zoom";
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
  const innerGRef = useRef<SVGGElement | null>(null);
  const [transform, setTransform] = useState<ZoomTransform>(zoomIdentity);
  // Manual drag overrides, keyed by node id.
  const [overrides, setOverrides] = useState<Map<string, { x: number; y: number }>>(
    new Map(),
  );
  const dragRef = useRef<{ id: string; moved: boolean } | null>(null);
  // Pointer capture retargets node clicks to the svg element, so e.target
  // can't distinguish a node click from a background click. This ref lets the
  // node pointerdown signal that the upcoming svg onClick should be skipped.
  const skipBackgroundClearRef = useRef(false);
  const zoomBehaviorRef = useRef<ZoomBehavior<SVGSVGElement, unknown> | null>(null);

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
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const n of simNodes) {
      minX = Math.min(minX, (n.x ?? 0) - n.radius);
      maxX = Math.max(maxX, (n.x ?? 0) + n.radius);
      minY = Math.min(minY, (n.y ?? 0) - n.radius);
      maxY = Math.max(maxY, (n.y ?? 0) + n.radius);
    }
    return { simNodes, simLinks, bounds: { minX, minY, maxX, maxY } };
  }, [nodes, links]);

  useEffect(() => {
    if (!svgRef.current) return;
    const behavior = zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.2, 6])
      .filter((event) => !(event.type === "mousedown" && dragRef.current))
      .on("zoom", (event) => setTransform(event.transform));
    zoomBehaviorRef.current = behavior;
    const sel = select(svgRef.current);
    sel.call(behavior);
    return () => {
      sel.on(".zoom", null);
    };
  }, []);

  // Fit the graph to the viewport whenever the layout changes.
  useEffect(() => {
    const svg = svgRef.current;
    const behavior = zoomBehaviorRef.current;
    if (!svg || !behavior) return;
    const { minX, minY, maxX, maxY } = layout.bounds;
    if (!Number.isFinite(minX)) return;
    const bw = Math.max(1, maxX - minX);
    const bh = Math.max(1, maxY - minY);
    const pad = 40; // label margin in viewBox units
    const k = Math.max(0.2, Math.min(6, Math.min(WIDTH / (bw + pad * 2), HEIGHT / (bh + pad * 2), 1)));
    const cx = (minX + maxX) / 2;
    const cy = (minY + maxY) / 2;
    // viewBox is centered on (0,0): translate so the bounds-center lands there.
    const t = zoomIdentity.translate(-cx * k, -cy * k).scale(k);
    select(svg).call(behavior.transform, t);
  }, [layout]);

  const pos = (n: LayoutNode) =>
    overrides.get(n.id) ?? { x: n.x ?? 0, y: n.y ?? 0 };

  const toGraphCoords = (clientX: number, clientY: number) => {
    const g = innerGRef.current;
    if (!g) return { x: 0, y: 0 };
    const ctm = g.getScreenCTM();
    if (!ctm) return { x: 0, y: 0 };
    const { x, y } = new DOMPoint(clientX, clientY).matrixTransform(ctm.inverse());
    return { x, y };
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
      onPointerCancel={() => {
        dragRef.current = null;
      }}
      onClick={() => {
        // Pointer capture retargets node clicks to the svg, so e.target can't
        // distinguish node vs background — the ref does.
        if (skipBackgroundClearRef.current) {
          skipBackgroundClearRef.current = false;
          return;
        }
        onSelect(null);
      }}
    >
      <g ref={innerGRef} transform={transform.toString()}>
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
                skipBackgroundClearRef.current = true;
                svgRef.current?.setPointerCapture(e.pointerId);
                dragRef.current = { id: n.id, moved: false };
              }}
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
