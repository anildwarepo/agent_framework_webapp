
// src/GraphViewer.tsx
import { useEffect, useState } from "react";
import ForceGraph3D from "react-force-graph-3d";
import SpriteText from "three-spritetext";

type Node = { id: string; group?: string; color?: string };
type Link = { source: string | Node; target: string | Node };
type GraphData = { nodes: Node[]; links: Link[] };

export default function GraphViewer() {
  const [data, setData] = useState<GraphData>({ nodes: [], links: [] });

  useEffect(() => {
    const url = new URL("./datasets/miserables.json", import.meta.url).href; // ✅ src/ relative
    fetch(url)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((g: GraphData) => setData(g))
      .catch((e) => console.error("Failed to load graph data:", e));
  }, []);

  return (
    <ForceGraph3D
      graphData={data}
      nodeAutoColorBy="group"
      nodeThreeObjectExtend
      nodeThreeObject={(n: any) => {
        const label = new SpriteText(String(n.id));
        label.textHeight = 8;
        label.color = n.color || "#ffffff";
        (label as any).position.set(0, 10, 0);
        return label;
      }}
    />
  );
}
