"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { Network, Search, X, Loader2 } from "lucide-react";
import { getPersons } from "@/lib/api";
import type { PersonSummary } from "@/lib/types";

interface GraphNode {
  id: string;
  name: string;
  company: string;
  confidence: number;
  x: number;
  y: number;
  vx: number;
  vy: number;
}

const COMPANY_COLORS = [
  "#3b82f6",
  "#8b5cf6",
  "#ec4899",
  "#f59e0b",
  "#10b981",
  "#06b6d4",
  "#6366f1",
  "#ef4444",
];

function hashCompany(company: string): number {
  let h = 0;
  for (let i = 0; i < company.length; i++) {
    h = (h << 5) - h + company.charCodeAt(i);
    h |= 0;
  }
  return Math.abs(h);
}

export default function NetworkGraphPage() {
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });
  const [transform, setTransform] = useState({ scale: 1, tx: 0, ty: 0 });
  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const dragRef = useRef<{ node: GraphNode; offsetX: number; offsetY: number } | null>(null);
  const panRef = useRef<{ startX: number; startY: number } | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getPersons(1, 100, search || undefined)
      .then((res) => {
        if (cancelled) return;
        const items = res.items || [];
        const centerX = dimensions.width / 2;
        const centerY = dimensions.height / 2;
        const radius = Math.min(dimensions.width, dimensions.height) * 0.35;
        const angleStep = (2 * Math.PI) / Math.max(items.length, 1);
        const newNodes: GraphNode[] = items.map((p: PersonSummary, i: number) => {
          const angle = i * angleStep;
          return {
            id: p.id,
            name: p.name,
            company: p.company || "Unknown",
            confidence: p.confidence_score ?? 0.5,
            x: centerX + radius * Math.cos(angle) + (Math.random() - 0.5) * 40,
            y: centerY + radius * Math.sin(angle) + (Math.random() - 0.5) * 40,
            vx: 0,
            vy: 0,
          };
        });
        setNodes(newNodes);
      })
      .catch(() => {
        if (!cancelled) setNodes([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [search]);

  const resizeObserver = useCallback(() => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    setDimensions({ width: rect.width, height: rect.height });
  }, []);

  useEffect(() => {
    resizeObserver();
    const ro = new ResizeObserver(resizeObserver);
    if (containerRef.current) ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, [resizeObserver]);

  const runSimulation = useCallback(() => {
    const REPULSION = 800;
    const CENTER_STRENGTH = 0.02;
    const DAMPING = 0.85;
    const MIN_DIST = 60;

    setNodes((prev) => {
      if (prev.length === 0) return prev;
      const centerX = dimensions.width / 2;
      const centerY = dimensions.height / 2;
      const next = prev.map((n) => ({ ...n }));

      for (let i = 0; i < next.length; i++) {
        let fx = 0;
        let fy = 0;

        for (let j = 0; j < next.length; j++) {
          if (i === j) continue;
          const dx = next[i].x - next[j].x;
          const dy = next[i].y - next[j].y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
          const minDist = MIN_DIST + (next[i].confidence + next[j].confidence) * 15;
          if (dist < minDist) {
            const force = REPULSION / (dist * dist);
            fx += (dx / dist) * force;
            fy += (dy / dist) * force;
          }
        }

        fx += (centerX - next[i].x) * CENTER_STRENGTH;
        fy += (centerY - next[i].y) * CENTER_STRENGTH;

        next[i].vx = (next[i].vx + fx * 0.1) * DAMPING;
        next[i].vy = (next[i].vy + fy * 0.1) * DAMPING;
        next[i].x += next[i].vx;
        next[i].y += next[i].vy;

        const margin = 40;
        next[i].x = Math.max(margin, Math.min(dimensions.width - margin, next[i].x));
        next[i].y = Math.max(margin, Math.min(dimensions.height - margin, next[i].y));
      }
      return next;
    });
  }, [dimensions]);

  useEffect(() => {
    if (nodes.length === 0) return;
    let rafId: number;
    const tick = () => {
      runSimulation();
      rafId = requestAnimationFrame(tick);
    };
    rafId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafId);
  }, [nodes.length, runSimulation]);

  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? -0.1 : 0.1;
    const newScale = Math.max(0.3, Math.min(3, transform.scale + delta));
    if (containerRef.current) {
      const rect = containerRef.current.getBoundingClientRect();
      const cx = e.clientX - rect.left;
      const cy = e.clientY - rect.top;
      const wx = (cx - transform.tx) / transform.scale;
      const wy = (cy - transform.ty) / transform.scale;
      setTransform({
        scale: newScale,
        tx: cx - wx * newScale,
        ty: cy - wy * newScale,
      });
    }
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.target instanceof SVGElement && e.target.closest("[data-node-id]")) return;
    panRef.current = { startX: e.clientX, startY: e.clientY };
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (dragRef.current) {
      const t = transform;
      const dx = (e.clientX - (panRef.current?.startX ?? e.clientX)) / t.scale;
      const dy = (e.clientY - (panRef.current?.startY ?? e.clientY)) / t.scale;
      setNodes((prev) =>
        prev.map((n) =>
          n.id === dragRef.current!.node.id
            ? { ...n, x: n.x + dx, y: n.y + dy, vx: 0, vy: 0 }
            : n
        )
      );
      if (panRef.current) {
        panRef.current.startX = e.clientX;
        panRef.current.startY = e.clientY;
      }
    } else if (panRef.current) {
      const dx = e.clientX - panRef.current.startX;
      const dy = e.clientY - panRef.current.startY;
      setTransform((t) => ({ ...t, tx: t.tx + dx, ty: t.ty + dy }));
      panRef.current.startX = e.clientX;
      panRef.current.startY = e.clientY;
    }
  };

  const handleMouseUp = () => {
    dragRef.current = null;
    panRef.current = null;
  };

  useEffect(() => {
    window.addEventListener("mouseup", handleMouseUp);
    return () => window.removeEventListener("mouseup", handleMouseUp);
  }, []);

  const searchLower = search.toLowerCase();
  const highlighted = searchLower
    ? nodes.filter(
        (n) =>
          n.name.toLowerCase().includes(searchLower) ||
          n.company.toLowerCase().includes(searchLower)
      )
    : null;

  return (
    <div className="flex flex-col h-[calc(100vh-2rem)]">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <Network size={28} />
          Network Graph
        </h1>
        <div className="relative w-64">
          <Search
            size={16}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500"
          />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search persons..."
            className="w-full bg-white/5 border border-white/10 rounded-lg pl-9 pr-8 py-2 text-white text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          {search && (
            <button
              onClick={() => setSearch("")}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 hover:text-white"
            >
              <X size={14} />
            </button>
          )}
        </div>
      </div>

      <div className="flex-1 flex gap-4 min-h-0">
        <div
          ref={containerRef}
          className="flex-1 rounded-xl border border-white/10 bg-white/[0.02] overflow-hidden relative"
          onWheel={handleWheel}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          style={{ touchAction: "none" }}
        >
          {loading ? (
            <div className="absolute inset-0 flex items-center justify-center">
              <Loader2 size={32} className="animate-spin text-blue-500" />
            </div>
          ) : (
            <svg
              ref={svgRef}
              width={dimensions.width}
              height={dimensions.height}
              className="block"
              style={{
                transform: `translate(${transform.tx}px, ${transform.ty}px) scale(${transform.scale})`,
                transformOrigin: "0 0",
              }}
            >
              <g>
                {nodes.map((node) => {
                  const color =
                    COMPANY_COLORS[hashCompany(node.company) % COMPANY_COLORS.length];
                  const isHighlighted =
                    !highlighted || highlighted.some((h) => h.id === node.id);
                  const isDimmed = highlighted && highlighted.length > 0 && !isHighlighted;
                  const r = 8 + node.confidence * 12;

                  return (
                    <g
                      key={node.id}
                      data-node-id={node.id}
                      transform={`translate(${node.x}, ${node.y})`}
                      style={{ cursor: "grab" }}
                      onMouseDown={(e) => {
                        e.stopPropagation();
                        if (containerRef.current) {
                          panRef.current = {
                            startX: e.clientX,
                            startY: e.clientY,
                          };
                          dragRef.current = {
                            node,
                            offsetX: 0,
                            offsetY: 0,
                          };
                        }
                      }}
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedNode(node);
                      }}
                    >
                      <circle
                        r={r}
                        fill={color}
                        fillOpacity={isDimmed ? 0.2 : 0.6}
                        stroke={selectedNode?.id === node.id ? "#fff" : "transparent"}
                        strokeWidth={2}
                      />
                      <text
                        x={0}
                        y={r + 14}
                        textAnchor="middle"
                        fill={isDimmed ? "#666" : "#fff"}
                        fontSize={10}
                        fontWeight={selectedNode?.id === node.id ? "bold" : "normal"}
                      >
                        {node.name}
                      </text>
                      {node.company && (
                        <text
                          x={0}
                          y={r + 26}
                          textAnchor="middle"
                          fill={isDimmed ? "#555" : "#9ca3af"}
                          fontSize={8}
                        >
                          {node.company}
                        </text>
                      )}
                    </g>
                  );
                })}
              </g>
            </svg>
          )}
        </div>

        {selectedNode && (
          <div className="w-72 rounded-xl border border-white/10 bg-white/[0.02] p-4 flex-col flex-shrink-0 overflow-y-auto">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-lg font-semibold text-white">Details</h3>
              <button
                onClick={() => setSelectedNode(null)}
                className="text-gray-500 hover:text-white"
              >
                <X size={18} />
              </button>
            </div>
            <div className="space-y-2 text-sm">
              <p className="text-white font-medium">{selectedNode.name}</p>
              <p className="text-gray-400 text-xs">{selectedNode.company}</p>
              <p className="text-gray-500">
                Confidence: {Math.round(selectedNode.confidence * 100)}%
              </p>
              <a
                href={`/admin/persons/${selectedNode.id}`}
                className="inline-block mt-2 text-blue-400 hover:text-blue-300 text-xs"
              >
                View full profile →
              </a>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
