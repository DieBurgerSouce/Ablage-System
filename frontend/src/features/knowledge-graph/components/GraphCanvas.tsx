/**
 * Graph Canvas Component
 * Interaktive SVG-basierte Graph-Visualisierung mit Force-Directed Layout
 */

import { useEffect, useRef, useState, useCallback } from 'react';
import type { GraphData, GraphNode, NodePosition } from '../types';

interface GraphCanvasProps {
  data: GraphData;
  onNodeSelect: (node: GraphNode) => void;
  selectedNodeId?: string;
}

const NODE_COLORS: Record<string, string> = {
  entity: '#3b82f6', // blue
  document: '#22c55e', // green
  invoice: '#f97316', // orange
  transaction: '#a855f7', // purple
  payment: '#14b8a6', // teal
};

const NODE_RADIUS = 20;
const LINK_DISTANCE = 120;
const CHARGE_STRENGTH = -300;
const GRAVITY_STRENGTH = 0.01;
const ITERATIONS = 300;

export function GraphCanvas({ data, onNodeSelect, selectedNodeId }: GraphCanvasProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [positions, setPositions] = useState<Map<string, NodePosition>>(new Map());
  const [viewport, setViewport] = useState({ zoom: 1, panX: 0, panY: 0 });
  const [dragging, setDragging] = useState<{ nodeId?: string; startX: number; startY: number } | null>(null);

  // Initialisiere Positionen und führe Force-Simulation aus
  useEffect(() => {
    if (data.nodes.length === 0) return;

    const width = svgRef.current?.clientWidth || 800;
    const height = svgRef.current?.clientHeight || 600;
    const centerX = width / 2;
    const centerY = height / 2;

    // Initialisiere zufällige Positionen
    const newPositions = new Map<string, NodePosition>();
    data.nodes.forEach((node) => {
      newPositions.set(node.id, {
        x: centerX + (Math.random() - 0.5) * 200,
        y: centerY + (Math.random() - 0.5) * 200,
        vx: 0,
        vy: 0,
      });
    });

    // Force-Simulation
    for (let i = 0; i < ITERATIONS; i++) {
      // Repulsion zwischen allen Knoten
      data.nodes.forEach((nodeA) => {
        const posA = newPositions.get(nodeA.id)!;
        data.nodes.forEach((nodeB) => {
          if (nodeA.id === nodeB.id) return;
          const posB = newPositions.get(nodeB.id)!;
          const dx = posB.x - posA.x;
          const dy = posB.y - posA.y;
          const distance = Math.sqrt(dx * dx + dy * dy) || 1;
          const force = CHARGE_STRENGTH / (distance * distance);
          posA.vx -= (dx / distance) * force;
          posA.vy -= (dy / distance) * force;
        });
      });

      // Spring-Kräfte auf Kanten
      data.edges.forEach((edge) => {
        const posSource = newPositions.get(edge.source);
        const posTarget = newPositions.get(edge.target);
        if (!posSource || !posTarget) return;

        const dx = posTarget.x - posSource.x;
        const dy = posTarget.y - posSource.y;
        const distance = Math.sqrt(dx * dx + dy * dy) || 1;
        const force = (distance - LINK_DISTANCE) * 0.01;
        const fx = (dx / distance) * force;
        const fy = (dy / distance) * force;

        posSource.vx += fx;
        posSource.vy += fy;
        posTarget.vx -= fx;
        posTarget.vy -= fy;
      });

      // Gravity zum Zentrum
      data.nodes.forEach((node) => {
        const pos = newPositions.get(node.id)!;
        pos.vx += (centerX - pos.x) * GRAVITY_STRENGTH;
        pos.vy += (centerY - pos.y) * GRAVITY_STRENGTH;
      });

      // Aktualisiere Positionen mit Dämpfung
      data.nodes.forEach((node) => {
        const pos = newPositions.get(node.id)!;
        pos.x += pos.vx;
        pos.y += pos.vy;
        pos.vx *= 0.9;
        pos.vy *= 0.9;
      });
    }

    setPositions(newPositions);
  }, [data]);

  // Mouse-Events für Drag & Pan
  const handleMouseDown = useCallback(
    (e: React.MouseEvent<SVGElement>, nodeId?: string) => {
      e.preventDefault();
      const svg = svgRef.current;
      if (!svg) return;

      const rect = svg.getBoundingClientRect();
      setDragging({
        nodeId,
        startX: (e.clientX - rect.left - viewport.panX) / viewport.zoom,
        startY: (e.clientY - rect.top - viewport.panY) / viewport.zoom,
      });
    },
    [viewport]
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent<SVGElement>) => {
      if (!dragging) return;
      const svg = svgRef.current;
      if (!svg) return;

      const rect = svg.getBoundingClientRect();
      const currentX = (e.clientX - rect.left - viewport.panX) / viewport.zoom;
      const currentY = (e.clientY - rect.top - viewport.panY) / viewport.zoom;

      if (dragging.nodeId) {
        // Knoten verschieben
        setPositions((prev) => {
          const newPositions = new Map(prev);
          const pos = newPositions.get(dragging.nodeId!);
          if (pos) {
            pos.x = currentX;
            pos.y = currentY;
          }
          return newPositions;
        });
      } else {
        // Pan
        const dx = currentX - dragging.startX;
        const dy = currentY - dragging.startY;
        setViewport((prev) => ({
          ...prev,
          panX: prev.panX + dx * viewport.zoom,
          panY: prev.panY + dy * viewport.zoom,
        }));
      }
    },
    [dragging, viewport]
  );

  const handleMouseUp = useCallback(() => {
    setDragging(null);
  }, []);

  const handleWheel = useCallback((e: React.WheelEvent<SVGElement>) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    setViewport((prev) => ({
      ...prev,
      zoom: Math.max(0.1, Math.min(5, prev.zoom * delta)),
    }));
  }, []);

  const handleNodeClick = useCallback(
    (node: GraphNode) => {
      onNodeSelect(node);
    },
    [onNodeSelect]
  );

  if (data.nodes.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-muted-foreground">
        <p>Keine Daten zum Anzeigen</p>
      </div>
    );
  }

  return (
    <svg
      ref={svgRef}
      className="h-full w-full cursor-move border border-border bg-background"
      onMouseDown={(e) => handleMouseDown(e)}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      onWheel={handleWheel}
    >
      <defs>
        <marker
          id="arrowhead"
          markerWidth="10"
          markerHeight="10"
          refX="9"
          refY="3"
          orient="auto"
          markerUnits="strokeWidth"
        >
          <path d="M0,0 L0,6 L9,3 z" fill="#64748b" />
        </marker>
      </defs>

      <g transform={`translate(${viewport.panX},${viewport.panY}) scale(${viewport.zoom})`}>
        {/* Kanten */}
        {data.edges.map((edge, idx) => {
          const posSource = positions.get(edge.source);
          const posTarget = positions.get(edge.target);
          if (!posSource || !posTarget) return null;

          return (
            <g key={`edge-${idx}`}>
              <line
                x1={posSource.x}
                y1={posSource.y}
                x2={posTarget.x}
                y2={posTarget.y}
                stroke="#64748b"
                strokeWidth={2}
                markerEnd="url(#arrowhead)"
              />
              <title>{edge.label}</title>
            </g>
          );
        })}

        {/* Knoten */}
        {data.nodes.map((node) => {
          const pos = positions.get(node.id);
          if (!pos) return null;

          const isSelected = node.id === selectedNodeId;
          const color = NODE_COLORS[node.type] || '#64748b';

          return (
            <g
              key={node.id}
              onMouseDown={(e) => {
                e.stopPropagation();
                handleMouseDown(e, node.id);
              }}
              onClick={() => handleNodeClick(node)}
              className="cursor-pointer"
            >
              {isSelected && (
                <circle cx={pos.x} cy={pos.y} r={NODE_RADIUS + 5} fill="none" stroke="#fbbf24" strokeWidth={3} />
              )}
              <circle cx={pos.x} cy={pos.y} r={NODE_RADIUS} fill={color} stroke="#fff" strokeWidth={2} />
              <text
                x={pos.x}
                y={pos.y + NODE_RADIUS + 16}
                textAnchor="middle"
                className="fill-foreground text-xs font-medium"
                style={{ pointerEvents: 'none' }}
              >
                {node.label.length > 20 ? node.label.slice(0, 20) + '...' : node.label}
              </text>
            </g>
          );
        })}
      </g>
    </svg>
  );
}
