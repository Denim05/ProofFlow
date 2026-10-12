"use client";

import React, { useEffect, useRef, useState, useMemo, useCallback } from "react";
import { EvidenceResponse, EventResponse } from "@/types/api";
import {
  RotateCcw,
  ZoomIn,
  ZoomOut,
  Shield,
  FileText,
  Clock,
  Sparkles,
  Layers,
} from "lucide-react";

interface EvidenceGraph3DProps {
  caseTitle: string;
  evidenceList: EvidenceResponse[];
  events?: EventResponse[];
}

interface Node3D {
  id: string;
  label: string;
  type: "CASE" | "EVIDENCE" | "EVENT";
  status?: string;
  meta?: string;
  x: number;
  y: number;
  z: number;
  size: number;
  color: string;
  glowColor: string;
}

interface Edge3D {
  sourceId: string;
  targetId: string;
  type: "EXTRACTION" | "ASSOCIATION" | "CHRONOLOGY";
  color: string;
  dashOffset: number;
}

export function EvidenceGraph3D({
  caseTitle,
  evidenceList,
  events = [],
}: EvidenceGraph3DProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  // Interaction State stored in refs to prevent unnecessary React re-renders & animation loop restarts
  const rotationRef = useRef({ yaw: 0.3, pitch: 0.2 });
  const zoomRef = useRef(1.1);
  const isDraggingRef = useRef(false);
  const lastMousePos = useRef({ x: 0, y: 0 });

  const hoveredNodeRef = useRef<Node3D | null>(null);
  const selectedNodeRef = useRef<Node3D | null>(null);

  const nodesRef = useRef<Node3D[]>([]);
  const edgesRef = useRef<Edge3D[]>([]);

  // React state for UI-visible changes only
  const [hoveredNode, setHoveredNode] = useState<Node3D | null>(null);
  const [selectedNode, setSelectedNode] = useState<Node3D | null>(null);
  const [viewMode, setViewMode] = useState<"ALL" | "DOCS_ONLY" | "CHRONO">("ALL");

  // Construct 3D Graph Structure
  const { nodes, edges } = useMemo(() => {
    const nList: Node3D[] = [];
    const eList: Edge3D[] = [];

    // 1. Center Node (The Incident Case)
    nList.push({
      id: "case-root",
      label: caseTitle || "Incident Case",
      type: "CASE",
      status: "ACTIVE",
      meta: `${evidenceList.length} docs, ${events.length} events`,
      x: 0,
      y: 0,
      z: 0,
      size: 14,
      color: "#00F2FE", // Neon Cyan
      glowColor: "rgba(0, 242, 254, 0.6)",
    });

    // 2. Evidence Document Nodes (Ring 1)
    const docCount = evidenceList.length;
    const docRadius = 160;

    evidenceList.forEach((doc, idx) => {
      const angle = (idx / Math.max(docCount, 1)) * Math.PI * 2;
      const x = Math.cos(angle) * docRadius;
      const y = Math.sin(angle) * docRadius * 0.45;
      const z = Math.sin(angle) * docRadius * 0.9;

      const isReady = doc.status === "READY";
      const isFailed = doc.status === "FAILED";
      const color = isFailed ? "#F43F5E" : isReady ? "#10B981" : "#38BDF8";
      const glow = isFailed
        ? "rgba(244, 63, 94, 0.5)"
        : isReady
        ? "rgba(16, 185, 129, 0.5)"
        : "rgba(56, 189, 248, 0.5)";

      const docNode: Node3D = {
        id: `doc-${doc.evidence_id}`,
        label: doc.original_filename,
        type: "EVIDENCE",
        status: doc.status,
        meta: `${(doc.file_size_bytes / 1024).toFixed(1)} KB • ${doc.media_type.replace("application/", "")}`,
        x,
        y,
        z,
        size: 9,
        color,
        glowColor: glow,
      };

      nList.push(docNode);

      // Edge from Case to Evidence
      eList.push({
        sourceId: "case-root",
        targetId: docNode.id,
        type: "ASSOCIATION",
        color: "rgba(0, 242, 254, 0.35)",
        dashOffset: 0,
      });
    });

    // 3. Event Milestone Nodes (Ring 2 or satellites around docs)
    if (viewMode !== "DOCS_ONLY") {
      const evtCount = Math.min(events.length, 16);
      const eventRadius = 260;
      const evtNodes: Node3D[] = [];

      events.slice(0, 16).forEach((evt, idx) => {
        const angle = (idx / Math.max(evtCount, 1)) * Math.PI * 2 + 0.35;
        const x = Math.cos(angle) * eventRadius;
        const y = Math.sin(angle) * eventRadius * 0.55 + (idx % 2 === 0 ? 30 : -30);
        const z = Math.sin(angle) * eventRadius * 0.8;

        const isDisputed = evt.decision_state === "REVIEW_NEEDED";
        const color = isDisputed ? "#F59E0B" : "#A78BFA";
        const glow = isDisputed ? "rgba(245, 158, 11, 0.6)" : "rgba(167, 139, 250, 0.45)";

        const description = evt.trigger_raw_text || evt.event_type;
        const evtNode: Node3D = {
          id: `evt-${evt.event_id}`,
          label: description.slice(0, 32) + (description.length > 32 ? "…" : ""),
          type: "EVENT",
          status: evt.decision_state,
          meta: evt.temporal_information || evt.created_at || "Undated",
          x,
          y,
          z,
          size: 6.5,
          color,
          glowColor: glow,
        };

        nList.push(evtNode);
        evtNodes.push(evtNode);

        // Connect event to its source evidence if matching, else root
        const targetDocId = evt.evidence_id ? `doc-${evt.evidence_id}` : "case-root";
        const hasDoc = nList.some((n) => n.id === targetDocId);

        eList.push({
          sourceId: hasDoc ? targetDocId : "case-root",
          targetId: evtNode.id,
          type: "EXTRACTION",
          color: isDisputed ? "rgba(245, 158, 11, 0.4)" : "rgba(167, 139, 250, 0.3)",
          dashOffset: 0,
        });
      });

      // In chronological mode, link successive events with chronology edges
      if (viewMode === "CHRONO" && evtNodes.length > 1) {
        for (let i = 0; i < evtNodes.length - 1; i++) {
          eList.push({
            sourceId: evtNodes[i].id,
            targetId: evtNodes[i + 1].id,
            type: "CHRONOLOGY",
            color: "rgba(167, 139, 250, 0.45)",
            dashOffset: 0,
          });
        }
      }
    }

    return { nodes: nList, edges: eList };
  }, [caseTitle, evidenceList, events, viewMode]);

  // Keep live references to nodes and edges for the animation loop
  nodesRef.current = nodes;
  edgesRef.current = edges;

  // Clean up selected/hovered nodes if filtered out by viewMode
  useEffect(() => {
    if (selectedNode && !nodes.some((n) => n.id === selectedNode.id)) {
      selectedNodeRef.current = null;
      setSelectedNode(null);
    }
    if (hoveredNode && !nodes.some((n) => n.id === hoveredNode.id)) {
      hoveredNodeRef.current = null;
      setHoveredNode(null);
    }
  }, [nodes, selectedNode, hoveredNode]);

  // Main 3D Canvas Rendering Loop — Stable effect that never restarts on frame updates
  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animId: number;

    // Detect and respect prefers-reduced-motion
    const mediaQuery =
      typeof window !== "undefined" && typeof window.matchMedia === "function"
        ? window.matchMedia("(prefers-reduced-motion: reduce)")
        : null;
    let prefersReducedMotion = mediaQuery ? mediaQuery.matches : false;

    const handleMediaChange = (e: MediaQueryListEvent) => {
      prefersReducedMotion = e.matches;
    };
    mediaQuery?.addEventListener?.("change", handleMediaChange);

    // Resize handling that prevents cumulative scaling
    const resize = () => {
      if (!container || !canvas) return;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const width = container.clientWidth;
      const height = container.clientHeight;
      if (width === 0 || height === 0) return;

      const targetWidth = Math.round(width * dpr);
      const targetHeight = Math.round(height * dpr);

      if (canvas.width !== targetWidth || canvas.height !== targetHeight) {
        canvas.width = targetWidth;
        canvas.height = targetHeight;
      }
    };

    resize();
    window.addEventListener("resize", resize);

    let ro: ResizeObserver | null = null;
    if (typeof ResizeObserver !== "undefined") {
      ro = new ResizeObserver(() => {
        resize();
      });
      ro.observe(container);
    }

    // Scroll wheel zoom on container
    const handleWheel = (e: WheelEvent) => {
      e.preventDefault();
      const delta = e.deltaY < 0 ? 0.08 : -0.08;
      zoomRef.current = Math.max(0.6, Math.min(2.2, zoomRef.current + delta));
    };
    container.addEventListener("wheel", handleWheel, { passive: false });

    // Global mouse-up listener so drag always releases
    const handleGlobalMouseUp = () => {
      isDraggingRef.current = false;
    };
    window.addEventListener("mouseup", handleGlobalMouseUp);

    let packetTime = 0;

    const render = () => {
      const width = container.clientWidth;
      const height = container.clientHeight;

      if (width > 0 && height > 0) {
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        // Explicit transform reset to avoid cumulative scaling
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, width, height);

        // Auto-rotation when not dragging and reduced motion is false
        if (!prefersReducedMotion && !isDraggingRef.current) {
          rotationRef.current.yaw += 0.003;
        }

        packetTime += 0.02;

        const rot = rotationRef.current;
        const currentZoom = zoomRef.current;
        const curHovered = hoveredNodeRef.current;
        const curSelected = selectedNodeRef.current;
        const curNodes = nodesRef.current;
        const curEdges = edgesRef.current;

        const centerX = width / 2;
        const centerY = height / 2;

        const cosY = Math.cos(rot.yaw);
        const sinY = Math.sin(rot.yaw);
        const cosP = Math.cos(rot.pitch);
        const sinP = Math.sin(rot.pitch);

        // 3D Projection Pipeline
        const fov = 450;
        const cameraDist = 500;

        const projectedNodes = curNodes.map((node) => {
          // Rotate Yaw (around Y axis)
          const x1 = node.x * cosY + node.z * sinY;
          const y1 = node.y;
          const z1 = -node.x * sinY + node.z * cosY;

          // Rotate Pitch (around X axis)
          const x2 = x1;
          const y2 = y1 * cosP - z1 * sinP;
          const z2 = y1 * sinP + z1 * cosP;

          // Apply Zoom & Perspective
          const scale = (fov / (fov + z2 + cameraDist)) * currentZoom * 1.5;
          const px = centerX + x2 * scale;
          const py = centerY + y2 * scale;

          return {
            ...node,
            px,
            py,
            depth: z2,
            projectedScale: scale,
          };
        });

        // Sort by depth (painter's algorithm)
        projectedNodes.sort((a, b) => b.depth - a.depth);

        // Node lookup map for edge rendering
        const nodeMap = new Map(projectedNodes.map((pn) => [pn.id, pn]));

        // 1. Draw Laser Conduits (Edges)
        curEdges.forEach((edge) => {
          const src = nodeMap.get(edge.sourceId);
          const tgt = nodeMap.get(edge.targetId);
          if (!src || !tgt) return;

          ctx.save();
          ctx.beginPath();
          ctx.moveTo(src.px, src.py);
          ctx.lineTo(tgt.px, tgt.py);
          ctx.strokeStyle = edge.color;
          ctx.lineWidth = Math.max(1, 1.2 * ((src.projectedScale + tgt.projectedScale) / 2));
          ctx.setLineDash([4, 6]);
          ctx.stroke();

          // Animated laser data pulse traveling down edge
          const t = (packetTime + (src.px % 10) * 0.1) % 1;
          const packetX = src.px + (tgt.px - src.px) * t;
          const packetY = src.py + (tgt.py - src.py) * t;

          ctx.beginPath();
          ctx.arc(packetX, packetY, 2, 0, Math.PI * 2);
          ctx.fillStyle = edge.color.replace("0.3", "0.9").replace("0.4", "0.9");
          ctx.shadowColor = edge.color;
          ctx.shadowBlur = 6;
          ctx.fill();
          ctx.restore();
        });

        // 2. Draw 3D Nodes
        projectedNodes.forEach((node) => {
          const radius = Math.max(3, node.size * node.projectedScale);
          const isHovered = curHovered?.id === node.id;
          const isSelected = curSelected?.id === node.id;

          ctx.save();

          // Ambient halo
          ctx.beginPath();
          ctx.arc(node.px, node.py, radius * 2.2, 0, Math.PI * 2);
          const haloGrad = ctx.createRadialGradient(
            node.px,
            node.py,
            radius * 0.5,
            node.px,
            node.py,
            radius * 2.4
          );
          haloGrad.addColorStop(0, node.glowColor);
          haloGrad.addColorStop(1, "transparent");
          ctx.fillStyle = haloGrad;
          ctx.fill();

          // Node sphere
          ctx.beginPath();
          ctx.arc(node.px, node.py, radius, 0, Math.PI * 2);
          ctx.fillStyle = node.color;
          ctx.shadowColor = node.color;
          ctx.shadowBlur = isHovered || isSelected ? 16 : 8;
          ctx.fill();

          // Border / Selection ring
          if (isSelected || isHovered) {
            ctx.beginPath();
            ctx.arc(node.px, node.py, radius + 4, 0, Math.PI * 2);
            ctx.strokeStyle = "#FFFFFF";
            ctx.lineWidth = 2;
            ctx.setLineDash([2, 2]);
            ctx.stroke();
          }

          // Label for Case Root, Hovered, Selected, or Foreground Nodes
          if (node.type === "CASE" || isHovered || isSelected || node.depth < -40) {
            ctx.font = `${Math.max(10, Math.round(11 * node.projectedScale))}px 'Geist Mono', monospace`;
            ctx.fillStyle = isHovered || isSelected ? "#FFFFFF" : "rgba(226, 232, 240, 0.85)";
            ctx.textAlign = "center";
            ctx.fillText(node.label, node.px, node.py + radius + 14);
          }

          ctx.restore();
        });
      }

      animId = requestAnimationFrame(render);
    };

    animId = requestAnimationFrame(render);

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener("resize", resize);
      window.removeEventListener("mouseup", handleGlobalMouseUp);
      container.removeEventListener("wheel", handleWheel);
      ro?.disconnect();
      mediaQuery?.removeEventListener?.("change", handleMediaChange);
    };
  }, []);

  // Mouse Interaction handlers for Pan / Orbit
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.button !== 0) return;
    isDraggingRef.current = true;
    lastMousePos.current = { x: e.clientX, y: e.clientY };
  }, []);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (isDraggingRef.current) {
      const dx = e.clientX - lastMousePos.current.x;
      const dy = e.clientY - lastMousePos.current.y;
      lastMousePos.current = { x: e.clientX, y: e.clientY };

      rotationRef.current.yaw += dx * 0.008;
      rotationRef.current.pitch = Math.max(
        -1.2,
        Math.min(1.2, rotationRef.current.pitch + dy * 0.008)
      );
      return;
    }

    // Raycasting hit test for node hovering
    const container = containerRef.current;
    if (!container) return;
    const rect = container.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    const centerX = rect.width / 2;
    const centerY = rect.height / 2;
    const fov = 450;
    const cameraDist = 500;

    const rot = rotationRef.current;
    const currentZoom = zoomRef.current;

    const cosY = Math.cos(rot.yaw);
    const sinY = Math.sin(rot.yaw);
    const cosP = Math.cos(rot.pitch);
    const sinP = Math.sin(rot.pitch);

    let bestHit: Node3D | null = null;
    let bestDepth = Infinity;
    const currentNodes = nodesRef.current;

    for (const node of currentNodes) {
      const x1 = node.x * cosY + node.z * sinY;
      const y1 = node.y;
      const z1 = -node.x * sinY + node.z * cosY;

      const x2 = x1;
      const y2 = y1 * cosP - z1 * sinP;
      const z2 = y1 * sinP + z1 * cosP;

      const scale = (fov / (fov + z2 + cameraDist)) * currentZoom * 1.5;
      const px = centerX + x2 * scale;
      const py = centerY + y2 * scale;
      const radius = Math.max(8, node.size * scale);

      const dist = Math.hypot(mouseX - px, mouseY - py);
      if (dist <= radius + 6) {
        if (z2 < bestDepth) {
          bestDepth = z2;
          bestHit = node;
        }
      }
    }

    const prevId = hoveredNodeRef.current?.id ?? null;
    const nextId = bestHit?.id ?? null;

    // Compare newly detected node ID with currently hovered node ID to avoid unnecessary state updates
    if (prevId !== nextId) {
      hoveredNodeRef.current = bestHit;
      setHoveredNode(bestHit);
    }
  }, []);

  const handleMouseUp = useCallback(() => {
    isDraggingRef.current = false;
  }, []);

  const handleMouseLeave = useCallback(() => {
    isDraggingRef.current = false;
    if (hoveredNodeRef.current !== null) {
      hoveredNodeRef.current = null;
      setHoveredNode(null);
    }
  }, []);

  const handleClick = useCallback(() => {
    const currentHovered = hoveredNodeRef.current;
    const currentSelected = selectedNodeRef.current;
    const nextSelected = currentHovered ?? null;

    if (currentSelected?.id !== nextSelected?.id) {
      selectedNodeRef.current = nextSelected;
      setSelectedNode(nextSelected);
    }
  }, []);

  const handleZoomIn = useCallback(() => {
    zoomRef.current = Math.min(2.2, zoomRef.current + 0.15);
  }, []);

  const handleZoomOut = useCallback(() => {
    zoomRef.current = Math.max(0.6, zoomRef.current - 0.15);
  }, []);

  const handleReset = useCallback(() => {
    rotationRef.current = { yaw: 0.3, pitch: 0.2 };
    zoomRef.current = 1.1;
  }, []);

  return (
    <div className="relative glass-panel rounded-2xl overflow-hidden border border-slate-800 shadow-2xl">
      {/* Network Header & Controls */}
      <div className="absolute top-4 left-4 z-20 flex items-center gap-2">
        <div className="px-3 py-1.5 rounded-xl bg-slate-900/90 border border-slate-700/80 backdrop-blur-md flex items-center gap-2 text-xs font-mono text-cyan-300 shadow-lg">
          <Sparkles className="w-3.5 h-3.5 text-cyan-400 animate-pulse" />
          <span>3D EVIDENCE TOPOLOGY MATRIX</span>
        </div>

        {/* View mode toggle */}
        <div className="flex items-center gap-1 bg-slate-900/90 border border-slate-800 rounded-xl p-1 backdrop-blur-md">
          {(["ALL", "DOCS_ONLY", "CHRONO"] as const).map((mode) => (
            <button
              key={mode}
              onClick={() => setViewMode(mode)}
              className={`px-2.5 py-1 text-[11px] font-mono rounded-lg transition ${
                viewMode === mode
                  ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              {mode}
            </button>
          ))}
        </div>
      </div>

      {/* Orbit & Zoom Controls Bar */}
      <div className="absolute top-4 right-4 z-20 flex items-center gap-1.5 bg-slate-900/90 border border-slate-800 rounded-xl p-1 backdrop-blur-md shadow-lg">
        <button
          onClick={handleZoomIn}
          className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition"
          title="Zoom In"
          aria-label="Zoom In"
        >
          <ZoomIn className="w-4 h-4" />
        </button>
        <button
          onClick={handleZoomOut}
          className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition"
          title="Zoom Out"
          aria-label="Zoom Out"
        >
          <ZoomOut className="w-4 h-4" />
        </button>
        <button
          onClick={handleReset}
          className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition"
          title="Reset View Orientation"
          aria-label="Reset View Orientation"
        >
          <RotateCcw className="w-4 h-4" />
        </button>
      </div>

      {/* Interactive 3D Canvas Stage */}
      <div
        ref={containerRef}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseLeave}
        onClick={handleClick}
        className="w-full h-[460px] cursor-grab active:cursor-grabbing relative bg-gradient-to-b from-slate-950/70 via-slate-950/90 to-slate-950/95"
      >
        <canvas ref={canvasRef} className="w-full h-full block" />

        {/* Selected or Hovered Node Info Overlay */}
        {(selectedNode || hoveredNode) && (
          <div className="absolute bottom-4 left-4 z-20 max-w-sm glass-panel-elevated p-4 rounded-xl border border-cyan-500/30 shadow-2xl animate-in fade-in duration-150 backdrop-blur-md">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-2">
                {selectedNode?.type === "EVIDENCE" || hoveredNode?.type === "EVIDENCE" ? (
                  <FileText className="w-4 h-4 text-emerald-400" />
                ) : selectedNode?.type === "EVENT" || hoveredNode?.type === "EVENT" ? (
                  <Clock className="w-4 h-4 text-violet-400" />
                ) : (
                  <Shield className="w-4 h-4 text-cyan-400" />
                )}
                <span className="text-xs font-mono uppercase tracking-wider text-cyan-300">
                  {(selectedNode || hoveredNode)?.type}
                </span>
              </div>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                {(selectedNode || hoveredNode)?.status}
              </span>
            </div>

            <h4 className="text-sm font-semibold text-white mt-1.5 line-clamp-1">
              {(selectedNode || hoveredNode)?.label}
            </h4>

            {(selectedNode || hoveredNode)?.meta && (
              <p className="text-xs font-mono text-slate-400 mt-1">
                {(selectedNode || hoveredNode)?.meta}
              </p>
            )}
          </div>
        )}

        {/* Empty Evidence Guide */}
        {evidenceList.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center p-6 pointer-events-none">
            <div className="glass-panel p-6 rounded-2xl text-center max-w-md border border-slate-800 backdrop-blur-md">
              <Layers className="w-8 h-8 text-cyan-400 mx-auto mb-2 opacity-80" />
              <h4 className="text-sm font-semibold text-white">Topology Awaiting Ingestion</h4>
              <p className="text-xs text-slate-400 mt-1">
                Upload documentary evidence to generate automated 3D relational nodes and cross-evidence links.
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Network Legend Footer */}
      <div className="px-5 py-3 border-t border-slate-800/80 bg-slate-950/60 flex flex-wrap items-center justify-between text-xs text-slate-400 font-mono gap-3">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 shadow-[0_0_6px_#00F2FE]" />
            <span>Case Nexus</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 shadow-[0_0_6px_#10B981]" />
            <span>Evidence File</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-violet-400 shadow-[0_0_6px_#A78BFA]" />
            <span>Extracted Milestone</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-amber-400 shadow-[0_0_6px_#F59E0B]" />
            <span>Disputed Link</span>
          </div>
        </div>

        <div className="text-[11px] text-slate-500">
          Drag to rotate • Scroll/controls to zoom
        </div>
      </div>
    </div>
  );
}

