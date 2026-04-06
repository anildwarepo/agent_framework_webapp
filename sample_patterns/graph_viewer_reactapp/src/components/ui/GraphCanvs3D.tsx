// src/components/ui/GraphCanvs3D.tsx
import React, {
  forwardRef, useImperativeHandle, useLayoutEffect, useRef, useState, useEffect
} from "react";
import ForceGraph3D, { ForceGraphMethods } from "react-force-graph-3d";
import SpriteText from "three-spritetext";
import * as THREE from "three";

type Node = { id: string; name?: string; color?: string; group?: string; label?: string; x?: number; y?: number; z?: number };
type Link = { source: string; target: string; weight?: number };
type GraphData = { nodes: Node[]; links: Link[] };
type Props = { graph: GraphData; onNodeClick?: (n: Node) => void };

/* ==== bright node palette (no pink/purple) ==== */
const BRIGHT = ["#06b6d4","#0ea5e9","#38bdf8","#22c55e","#10b981","#84cc16","#eab308","#f97316"];
const hash = (s: string) => { let h = 2166136261; for (let i=0;i<s.length;i++){ h^=s.charCodeAt(i); h=Math.imul(h,16777619);} return (h>>>0); };
const colorFor = (n: Node) => BRIGHT[hash(String(n.group ?? n.label ?? n.name ?? n.id)) % BRIGHT.length];

/* ==== edge style (tweak here) ==== */
const EDGE_COLOR = "#cbd5e1";     // slate-300 (bright neutral)
const EDGE_OPACITY = 0.95;        // almost solid
const EDGE_WIDTH_BASE = 0.3;      // thicker lines
const EDGE_WIDTH_MAX = 3;

/* container size observer */
function useContainerSize() {
  const ref = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  useLayoutEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([entry]) => {
      const cr = entry.contentRect;
      setSize({ w: Math.round(cr.width), h: Math.round(cr.height) });
    });
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, size] as const;
}

const GraphCanvs3D = forwardRef<ForceGraphMethods, Props>(({ graph, onNodeClick }, ref) => {
  const [wrapRef, size] = useContainerSize();
  const fgRef = useRef<ForceGraphMethods | undefined>(undefined);
  useImperativeHandle(ref, () => fgRef.current as ForceGraphMethods);

  const zoomToFitSafe = (ms = 500) => {
    if (!fgRef.current) return;
    requestAnimationFrame(() => fgRef.current?.zoomToFit?.(ms, 60));
  };

  useEffect(() => { if (size.w && size.h) zoomToFitSafe(400); }, [size.w, size.h]);
  useEffect(() => { zoomToFitSafe(500); }, [graph]);

  return (
    <div ref={wrapRef} style={{ position: "relative", width: "100%", height: "100%" }}>
      <ForceGraph3D
        ref={fgRef as any}
        graphData={graph}
        width={size.w || undefined}
        height={size.h || undefined}
        backgroundColor="#0B1220"
        rendererConfig={{ antialias: true, alpha: false }}
        d3AlphaDecay={0.05}
        d3VelocityDecay={0.35}
        onEngineStop={() => zoomToFitSafe(300)}
        onNodeClick={onNodeClick as any}

        /* === opaque custom sphere + white label === */
        nodeThreeObjectExtend={false}
        nodeThreeObject={(n: any) => {
          const col = new THREE.Color(colorFor(n));
          const group = new THREE.Group();

          const r = 5;
          const geom = new THREE.SphereGeometry(r, 24, 24);
          const mat = new THREE.MeshStandardMaterial({
            color: col,
            emissive: col.clone().multiplyScalar(0.18),
            emissiveIntensity: 0.6,
            metalness: 0.2,
            roughness: 0.35,
            transparent: false
          });
          group.add(new THREE.Mesh(geom, mat));

          const label = new SpriteText(String(n.name ?? n.id));
          label.color = "#f8fafc";
          label.textHeight = 6;
          (label.material as any).depthWrite = false;
          (label.material as any).depthTest  = false;
          (label.material as any).transparent = true;
          label.position.set(0, r + 6, 0);
          group.add(label);

          return group;
        }}

        /* === prominent edges === */
        linkColor={() => EDGE_COLOR}
        linkOpacity={EDGE_OPACITY}
        linkWidth={(l: any) => {
          // scale by optional link.weight if present, else constant
          const w = typeof l?.weight === "number" ? Math.min(EDGE_WIDTH_MAX, EDGE_WIDTH_BASE + l.weight) : EDGE_WIDTH_BASE;
          return w;
        }}
        // optional: subtle motion highlights (enable if you like)
        // linkDirectionalParticles={1}
        // linkDirectionalParticleWidth={2}
        // linkDirectionalParticleColor={() => EDGE_COLOR}
      />
    </div>
  );
});

export default GraphCanvs3D;
