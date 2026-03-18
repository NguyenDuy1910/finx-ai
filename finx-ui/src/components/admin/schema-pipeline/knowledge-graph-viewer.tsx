"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import type { KGNode, KGEdge } from "@/types/schema-pipeline.types";

// ── Types ──────────────────────────────────────────────────────────────────

interface Props {
    nodes: KGNode[];
    edges: KGEdge[];
    /** Optional CSS height (default "400px") */
    height?: string;
}

interface PositionedNode extends KGNode {
    x: number;
    y: number;
    vx: number;
    vy: number;
}

// ── Color palette by node type ─────────────────────────────────────────────

const NODE_COLORS: Record<string, { fill: string; stroke: string; text: string }> = {
    table: { fill: "#3b82f6", stroke: "#2563eb", text: "#ffffff" },
    column: { fill: "#8b5cf6", stroke: "#7c3aed", text: "#ffffff" },
    domain: { fill: "#10b981", stroke: "#059669", text: "#ffffff" },
    entity: { fill: "#f59e0b", stroke: "#d97706", text: "#ffffff" },
    concept: { fill: "#ec4899", stroke: "#db2777", text: "#ffffff" },
    default: { fill: "#6b7280", stroke: "#4b5563", text: "#ffffff" },
};

const EDGE_COLORS: Record<string, string> = {
    structural: "#334155",
    semantic: "#6366f1",
    business: "#0ea5e9",
    default: "#475569",
};

const NODE_RADIUS = 22;
const LABEL_MAX_WIDTH = 15; // chars

function truncate(s: string, n: number) {
    return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

// ── Force-directed layout (simple spring simulation) ──────────────────────

function initPositions(nodes: KGNode[], width: number, height: number): PositionedNode[] {
    return nodes.map((n, i) => {
        const angle = (2 * Math.PI * i) / Math.max(nodes.length, 1);
        const r = Math.min(width, height) * 0.3;
        return {
            ...n,
            x: width / 2 + r * Math.cos(angle),
            y: height / 2 + r * Math.sin(angle),
            vx: 0,
            vy: 0,
        };
    });
}

function simulate(
    nodes: PositionedNode[],
    edges: KGEdge[],
    width: number,
    height: number,
    iterations: number = 80
): PositionedNode[] {
    const lookup = new Map(nodes.map((n) => [n.id, n]));
    const k = 1 / Math.max(nodes.length, 1);
    const idealDist = Math.min(width, height) * 0.3;

    for (let iter = 0; iter < iterations; iter++) {
        const alpha = 1 - iter / iterations;

        // Repulsion between all pairs
        for (let i = 0; i < nodes.length; i++) {
            for (let j = i + 1; j < nodes.length; j++) {
                const a = nodes[i], b = nodes[j];
                const dx = b.x - a.x || 0.1;
                const dy = b.y - a.y || 0.1;
                const dist = Math.sqrt(dx * dx + dy * dy) || 1;
                const force = (idealDist * idealDist) / dist;
                const fx = (dx / dist) * force * alpha * 0.5;
                const fy = (dy / dist) * force * alpha * 0.5;
                a.vx -= fx; a.vy -= fy;
                b.vx += fx; b.vy += fy;
            }
        }

        // Attraction along edges
        for (const edge of edges) {
            const a = lookup.get(edge.source);
            const b = lookup.get(edge.target);
            if (!a || !b) continue;
            const dx = b.x - a.x;
            const dy = b.y - a.y;
            const dist = Math.sqrt(dx * dx + dy * dy) || 1;
            const force = (dist - idealDist) * k * 0.5 * alpha;
            const fx = (dx / dist) * force;
            const fy = (dy / dist) * force;
            a.vx += fx; a.vy += fy;
            b.vx -= fx; b.vy -= fy;
        }

        // Center gravity
        for (const n of nodes) {
            n.vx += (width / 2 - n.x) * 0.01 * alpha;
            n.vy += (height / 2 - n.y) * 0.01 * alpha;
        }

        // Apply velocities
        for (const n of nodes) {
            n.x = Math.max(NODE_RADIUS + 10, Math.min(width - NODE_RADIUS - 10, n.x + n.vx));
            n.y = Math.max(NODE_RADIUS + 20, Math.min(height - NODE_RADIUS - 20, n.y + n.vy));
            n.vx *= 0.6;
            n.vy *= 0.6;
        }
    }
    return nodes;
}

// ── Main Component ─────────────────────────────────────────────────────────

export function KnowledgeGraphViewer({ nodes, edges, height = "420px" }: Props) {
    const svgRef = useRef<SVGSVGElement>(null);
    const containerRef = useRef<HTMLDivElement>(null);
    const [positioned, setPositioned] = useState<PositionedNode[]>([]);
    const [tooltip, setTooltip] = useState<{ node: PositionedNode; x: number; y: number } | null>(null);
    const [dimensions, setDimensions] = useState({ width: 600, height: 420 });

    // Measure container
    useEffect(() => {
        const el = containerRef.current;
        if (!el) return;
        const ro = new ResizeObserver(() => {
            setDimensions({ width: el.clientWidth, height: el.clientHeight });
        });
        ro.observe(el);
        setDimensions({ width: el.clientWidth, height: el.clientHeight });
        return () => ro.disconnect();
    }, []);

    // (Re)compute layout whenever nodes/edges/dimensions change
    useEffect(() => {
        if (!nodes.length) { setPositioned([]); return; }
        const initial = initPositions(nodes, dimensions.width, dimensions.height);
        const result = simulate([...initial], edges, dimensions.width, dimensions.height, 100);
        setPositioned(result);
    }, [nodes, edges, dimensions]);

    const lookup = new Map(positioned.map((n) => [n.id, n]));

    if (!nodes.length) {
        return (
            <div
                style={{ height }}
                className="flex items-center justify-center rounded-xl border border-border/40 bg-muted/20 text-sm text-muted-foreground"
            >
                No knowledge graph data available yet.
            </div>
        );
    }

    return (
        <div ref={containerRef} style={{ height }} className="relative overflow-hidden rounded-xl border border-border/40 bg-[#0d1117]">
            <svg
                ref={svgRef}
                width="100%"
                height="100%"
                viewBox={`0 0 ${dimensions.width} ${dimensions.height}`}
                className="select-none"
                onMouseLeave={() => setTooltip(null)}
            >
                <defs>
                    {/* Arrowhead markers by edge type */}
                    {Object.entries(EDGE_COLORS).map(([type, color]) => (
                        <marker
                            key={type}
                            id={`arrow-${type}`}
                            markerWidth="8"
                            markerHeight="8"
                            refX="6"
                            refY="3"
                            orient="auto"
                            markerUnits="userSpaceOnUse"
                        >
                            <path d="M0,0 L0,6 L8,3 z" fill={color} />
                        </marker>
                    ))}
                </defs>

                {/* Edges */}
                {edges.map((edge, i) => {
                    const src = lookup.get(edge.source);
                    const tgt = lookup.get(edge.target);
                    if (!src || !tgt || src === tgt) return null;
                    // Shorten line to node radius
                    const dx = tgt.x - src.x;
                    const dy = tgt.y - src.y;
                    const dist = Math.sqrt(dx * dx + dy * dy) || 1;
                    const r = NODE_RADIUS;
                    const x1 = src.x + (dx / dist) * r;
                    const y1 = src.y + (dy / dist) * r;
                    const x2 = tgt.x - (dx / dist) * (r + 8);
                    const y2 = tgt.y - (dy / dist) * (r + 8);
                    const color = EDGE_COLORS[edge.type] || EDGE_COLORS.default;
                    // Label midpoint
                    const mx = (x1 + x2) / 2;
                    const my = (y1 + y2) / 2;
                    return (
                        <g key={i}>
                            <line
                                x1={x1} y1={y1} x2={x2} y2={y2}
                                stroke={color}
                                strokeWidth={1.5}
                                strokeOpacity={0.7}
                                markerEnd={`url(#arrow-${edge.type || "default"})`}
                            />
                            {edge.label && dist > 80 && (
                                <text
                                    x={mx} y={my - 5}
                                    textAnchor="middle"
                                    fontSize={9}
                                    fill={color}
                                    opacity={0.8}
                                    className="pointer-events-none"
                                >
                                    {truncate(edge.label, 18)}
                                </text>
                            )}
                        </g>
                    );
                })}

                {/* Nodes */}
                {positioned.map((node) => {
                    const colors = NODE_COLORS[node.type] || NODE_COLORS.default;
                    return (
                        <g
                            key={node.id}
                            transform={`translate(${node.x},${node.y})`}
                            onMouseEnter={(e) => {
                                const svgRect = svgRef.current?.getBoundingClientRect();
                                if (svgRect) {
                                    setTooltip({ node, x: node.x, y: node.y });
                                }
                            }}
                            onMouseLeave={() => setTooltip(null)}
                            className="cursor-pointer"
                        >
                            <circle
                                r={NODE_RADIUS}
                                fill={colors.fill}
                                stroke={colors.stroke}
                                strokeWidth={2}
                                className="transition-all duration-150 hover:r-[26]"
                                style={{ filter: "drop-shadow(0 2px 4px rgba(0,0,0,0.4))" }}
                            />
                            <text
                                textAnchor="middle"
                                dominantBaseline="middle"
                                fontSize={9}
                                fill={colors.text}
                                fontWeight={600}
                                className="pointer-events-none"
                            >
                                {truncate(node.label, LABEL_MAX_WIDTH)}
                            </text>
                            {/* Type badge */}
                            <text
                                y={NODE_RADIUS + 12}
                                textAnchor="middle"
                                fontSize={8}
                                fill="#64748b"
                                className="pointer-events-none"
                            >
                                {node.type}
                            </text>
                        </g>
                    );
                })}

                {/* Tooltip */}
                {tooltip && (() => {
                    const n = tooltip.node;
                    const tw = 180, th = 60;
                    let tx = n.x + NODE_RADIUS + 8;
                    let ty = n.y - th / 2;
                    if (tx + tw > dimensions.width) tx = n.x - NODE_RADIUS - tw - 8;
                    if (ty < 4) ty = 4;
                    if (ty + th > dimensions.height) ty = dimensions.height - th - 4;
                    return (
                        <g className="pointer-events-none">
                            <rect
                                x={tx} y={ty} width={tw} height={th}
                                rx={6} ry={6}
                                fill="#1e293b"
                                stroke="#334155"
                                strokeWidth={1}
                            />
                            <text x={tx + 10} y={ty + 18} fontSize={11} fill="#f1f5f9" fontWeight={600}>
                                {truncate(n.label, 20)}
                            </text>
                            <text x={tx + 10} y={ty + 33} fontSize={9} fill="#64748b">
                                Type: {n.type}
                            </text>
                            {n.description && (
                                <text x={tx + 10} y={ty + 47} fontSize={9} fill="#94a3b8">
                                    {truncate(n.description, 26)}
                                </text>
                            )}
                        </g>
                    );
                })()}
            </svg>

            {/* Legend */}
            <div className="absolute bottom-3 left-3 flex flex-wrap gap-2">
                {Object.entries(NODE_COLORS).filter(([k]) => k !== "default").map(([type, colors]) => (
                    <div key={type} className="flex items-center gap-1">
                        <span
                            className="inline-block h-2.5 w-2.5 rounded-full"
                            style={{ background: colors.fill }}
                        />
                        <span className="text-[10px] text-slate-400 capitalize">{type}</span>
                    </div>
                ))}
            </div>
        </div>
    );
}
