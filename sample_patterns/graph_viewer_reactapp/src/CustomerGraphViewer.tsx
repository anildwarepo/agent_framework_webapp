import { useEffect, useRef, useState } from "react";
import Breadcrumbs from "@/components/ui/Breadcrumbs";
import GraphCanvs3D from "@/components/ui/GraphCanvs3D";
import { GraphAPI } from "@/api/graph";
import { loadInitialGraph } from "@/api/initialGraph";
import { toGraph } from "@/graph/transform";
import type { GraphData, NavLevel } from "@/graph/types";
import type { ForceGraphMethods } from "react-force-graph-3d";

export default function CustomerGraphViewer() {
  const [levels, setLevels] = useState<NavLevel[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [data, setData] = useState<GraphData>({ nodes: [], links: [] });
  const [loading, setLoading] = useState(false);
  const fgRef = useRef<ForceGraphMethods>(null);

  // load root graph
  useEffect(() => {
    let active = true;
    (async () => {
      setLoading(true);
      try {
        const g = await loadInitialGraph();
        if (!active) return;
        setLevels([{ title: "All", graph: g }]);
        setCurrentIndex(0);
        setData(g);
      } finally {
        setLoading(false);
      }
    })();
    return () => { active = false; };
  }, []);

  function jumpToLevel(index: number) {
    setCurrentIndex(index);
    const lvl = levels[index];
    if (lvl) setData(lvl.graph);
  }

  async function handleNodeClick(n: any) {
    const nodeId = String(n.id);
    const title = String(n.name || n.id);
    setLoading(true);
    try {
      const items = await GraphAPI.nodeNeighborhood(nodeId);
      const subgraph = toGraph(items);
      setLevels(prev => [...prev.slice(0, currentIndex + 1), { title, clickedNodeId: nodeId, graph: subgraph }]);
      setCurrentIndex(i => i + 1);
      setData(subgraph);
    } catch (err) {
      console.error(`Failed to fetch neighborhood for ${nodeId}:`, err);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0, background: "#0B1220" }}>
      <Breadcrumbs levels={levels} currentIndex={currentIndex} onJump={jumpToLevel} />

      {loading && (
        <div
          style={{
            height: 2,
            background: "linear-gradient(90deg, #60a5fa, #34d399, #a78bfa)",
            animation: "load 1.2s linear infinite",
            backgroundSize: "200% 100%"
          }}
        />
      )}

      {/* canvas fills & centers itself via GraphCanvs3D */}
      <div style={{ flex: 1, minHeight: 0 }}>
        <GraphCanvs3D ref={fgRef as any} graph={data} onNodeClick={handleNodeClick} />
      </div>

      <style>{`
        @keyframes load {
          0% { background-position: 0% 50%; }
          100% { background-position: 100% 50%; }
        }
      `}</style>
    </div>
  );
}
