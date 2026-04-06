// src/components/ui/GraphCanvs3D.tsx
import {
  forwardRef, useImperativeHandle, useLayoutEffect, useRef, useState, useEffect
} from "react";
import ForceGraph3D, { ForceGraphMethods } from "react-force-graph-3d";
import SpriteText from "three-spritetext";
import * as THREE from "three";

type Node = { id: string; name?: string; color?: string; group?: string; label?: string; raw?: any; x?: number; y?: number; z?: number };
type Link = { source: string; target: string; weight?: number };
type GraphData = { nodes: Node[]; links: Link[] };
type Props = {
  graph: GraphData;
  onNodeClick?: (n: Node) => void;
  onNodeSelect?: (n: Node | null) => void;
};

/* ==== bright node palette (no pink/purple) ==== */
const BRIGHT = ["#06b6d4","#0ea5e9","#38bdf8","#22c55e","#10b981","#84cc16","#eab308","#f97316"];
const hash = (s: string) => { let h = 2166136261; for (let i=0;i<s.length;i++){ h^=s.charCodeAt(i); h=Math.imul(h,16777619);} return (h>>>0); };
const colorFor = (n: Node) => BRIGHT[hash(String(n.group ?? n.label ?? n.name ?? n.id)) % BRIGHT.length];

/* ==== edge style ==== */
const EDGE_COLOR = "#cbd5e1";
const EDGE_OPACITY = 0.95;
const EDGE_WIDTH_BASE = 0.3;
const EDGE_WIDTH_MAX = 3;

/* ==== Shared geometries & materials ==== */
const SPHERE_GEO = new THREE.SphereGeometry(5, 12, 8);
const MAT_CACHE = new Map<string, THREE.MeshLambertMaterial>();
function getMat(hex: string): THREE.MeshLambertMaterial {
  let m = MAT_CACHE.get(hex);
  if (!m) {
    const c = new THREE.Color(hex);
    m = new THREE.MeshLambertMaterial({ color: c, emissive: c.clone().multiplyScalar(0.15) });
    MAT_CACHE.set(hex, m);
  }
  return m;
}

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

const GraphCanvs3D = forwardRef<ForceGraphMethods, Props>(({ graph, onNodeClick, onNodeSelect }, ref) => {
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
        rendererConfig={{ antialias: false, alpha: false, powerPreference: "high-performance" }}
        d3AlphaDecay={0.08}
        d3VelocityDecay={0.4}
        warmupTicks={30}
        cooldownTicks={200}
        onEngineStop={() => zoomToFitSafe(300)}
        onNodeClick={(n: any) => {
          onNodeSelect?.(n);
          onNodeClick?.(n);
        }}
        onBackgroundClick={() => onNodeSelect?.(null)}

        nodeThreeObjectExtend={false}
        nodeThreeObject={(n: any) => {
          const hex = colorFor(n);
          const group = new THREE.Group();
          group.add(new THREE.Mesh(SPHERE_GEO, getMat(hex)));

          const label = new SpriteText(String(n.name ?? n.id));
          label.color = "#f8fafc";
          label.textHeight = 6;
          (label.material as any).depthWrite = false;
          (label.material as any).depthTest  = false;
          (label.material as any).transparent = true;
          label.position.set(0, 11, 0);
          group.add(label);

          return group;
        }}

        linkColor={() => EDGE_COLOR}
        linkOpacity={EDGE_OPACITY}
        linkWidth={(l: any) => {
          const w = typeof l?.weight === "number" ? Math.min(EDGE_WIDTH_MAX, EDGE_WIDTH_BASE + l.weight) : EDGE_WIDTH_BASE;
          return w;
        }}
      />
    </div>
  );
});

export default GraphCanvs3D;
