import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import Breadcrumbs from "@/components/ui/Breadcrumbs";
import GraphCanvs3D from "@/components/ui/GraphCanvs3D";
import NodePropertiesPanel from "@/components/ui/NodePropertiesPanel";
import { GraphAPI } from "@/api/graph";
import type { DiscoverLabel } from "@/api/graph";
import { toGraph, stripAgtype, parseLabel } from "@/graph/transform";
import { colorForLabel } from "@/graph/colors";
import type { GraphData, NavLevel, Node } from "@/graph/types";
import type { ForceGraphMethods } from "react-force-graph-3d";

type Props = {
  open: boolean;
  onClose: () => void;
  graphName: string;
};

/** Parse AGE label value: '["City_Council_Meeting"]' → 'City_Council_Meeting' */
function cleanLabel(raw: string): string {
  return parseLabel(raw) ?? stripAgtype(raw);
}

/** Convert discover_labels response into a GraphData where each label is a node */
function labelsToGraph(labels: DiscoverLabel[]): GraphData {
  const nodes = labels.map((l) => {
    const lbl = cleanLabel(String(l.label));
    const cnt = typeof l.cnt === "string" ? parseInt(stripAgtype(String(l.cnt)), 10) : l.cnt;
    let sampleName = "";
    try {
      const p = typeof l.sample_payload === "string" ? JSON.parse(l.sample_payload) : l.sample_payload;
      sampleName = p?.name ?? "";
    } catch { /* ignore */ }

    return {
      id: lbl,
      group: lbl,
      color: colorForLabel(lbl),
      name: `${lbl} (${cnt})`,
      raw: { label: lbl, count: cnt, sample_name: sampleName },
      _isLabel: true,
    };
  });
  return { nodes, links: [] };
}

export default function GraphViewerDialog({ open, onClose, graphName }: Props) {
  const [levels, setLevels] = useState<NavLevel[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [data, setData] = useState<GraphData>({ nodes: [], links: [] });
  const [loading, setLoading] = useState(false);
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const fgRef = useRef<ForceGraphMethods>(null);

  // Load label overview on open
  useEffect(() => {
    if (!open) return;
    let active = true;
    (async () => {
      setLoading(true);
      try {
        const labels = await GraphAPI.discoverLabels(graphName);
        if (!active) return;
        const g = labelsToGraph(labels);
        setLevels([{ title: "All Labels", graph: g }]);
        setCurrentIndex(0);
        setData(g);
      } catch (err) {
        console.error("Failed to discover labels:", err);
      } finally {
        setLoading(false);
      }
    })();
    return () => { active = false; };
  }, [open, graphName]);

  function jumpToLevel(index: number) {
    setCurrentIndex(index);
    setSelectedNode(null);
    const lvl = levels[index];
    if (lvl) setData(lvl.graph);
  }

  // Track which nodes have been expanded so we don't re-fetch
  const expandedRef = useRef<Set<string>>(new Set());

  // Reset expanded set when navigating levels
  useEffect(() => { expandedRef.current = new Set(); }, [currentIndex]);

  async function handleNodeClick(n: any) {
    const nodeId = String(n.id);
    const title = String(n.name || n.id);

    if (n._isLabel) {
      // Level 0: clicked a label node → navigate to nodes of that label
      const currentLevel = levels[currentIndex];
      if (currentLevel?.clickedNodeId === nodeId) return;

      setLoading(true);
      try {
        const items = await GraphAPI.nodesByLabel(graphName, nodeId, 100);
        const subgraph = toGraph(items);
        if (subgraph.nodes.length === 0) return;
        setLevels(prev => [...prev.slice(0, currentIndex + 1), { title, clickedNodeId: nodeId, graph: subgraph }]);
        setCurrentIndex(i => i + 1);
        setData(subgraph);
      } catch (err) {
        console.error(`Failed to fetch label nodes for ${nodeId}:`, err);
      } finally {
        setLoading(false);
      }
      return;
    }

    // Individual node: expand in place — add neighbors to current graph
    if (expandedRef.current.has(nodeId)) return; // already expanded
    expandedRef.current.add(nodeId);

    setLoading(true);
    try {
      const items = await GraphAPI.nodeNeighborhood(graphName, nodeId);
      const neighborhood = toGraph(items);

      if (neighborhood.nodes.length <= 1) return; // no neighbors

      // Merge into current graph
      setData(prev => {
        const existingNodeIds = new Set(prev.nodes.map(nd => nd.id));
        const existingLinkKeys = new Set(prev.links.map(l => `${l.source}→${l.target}`));

        const newNodes = neighborhood.nodes.filter(nd => !existingNodeIds.has(nd.id));

        // Use real links from the neighborhood
        const newLinks = neighborhood.links.filter(l => {
          const key = `${l.source}→${l.target}`;
          return !existingLinkKeys.has(key);
        });

        // If there are no real edges, create synthetic links from clicked node to each new neighbor
        if (newLinks.length === 0 && newNodes.length > 0) {
          for (const nd of newNodes) {
            const fwd = `${nodeId}→${nd.id}`;
            const rev = `${nd.id}→${nodeId}`;
            if (!existingLinkKeys.has(fwd) && !existingLinkKeys.has(rev)) {
              newLinks.push({ source: nodeId, target: nd.id });
            }
          }
        }

        if (newNodes.length === 0 && newLinks.length === 0) return prev;

        return {
          nodes: [...prev.nodes, ...newNodes],
          links: [...prev.links, ...newLinks],
        };
      });
    } catch (err) {
      console.error(`Failed to expand node ${nodeId}:`, err);
      expandedRef.current.delete(nodeId);
    } finally {
      setLoading(false);
    }
  }

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col bg-[#0B1220]"
      role="dialog"
      aria-modal="true"
      aria-label="Graph Viewer"
    >
      {/* Top bar */}
      <div className="shrink-0 flex items-center justify-between px-4 py-2 border-b border-slate-700 bg-slate-800/90 backdrop-blur">
        <h2 className="text-sm font-semibold text-slate-100">Graph Viewer</h2>
        <button
          type="button"
          onClick={onClose}
          className="text-slate-400 hover:text-slate-100 p-1 rounded hover:bg-slate-700 transition-colors"
          aria-label="Close graph viewer"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      <Breadcrumbs levels={levels} currentIndex={currentIndex} onJump={jumpToLevel} />

      {loading && (
        <div
          style={{
            height: 2,
            background: "linear-gradient(90deg, #60a5fa, #34d399, #a78bfa)",
            animation: "graphload 1.2s linear infinite",
            backgroundSize: "200% 100%",
          }}
        />
      )}

      {/* Graph canvas + property panel */}
      <div className="flex-1 min-h-0 flex overflow-hidden">
        {/* Graph canvas */}
        <div className="flex-1 min-w-0 relative" style={{ zIndex: 1 }}>
          <GraphCanvs3D
            ref={fgRef as any}
            graph={data}
            onNodeClick={handleNodeClick}
            onNodeSelect={(n) => setSelectedNode(n as Node | null)}
          />
        </div>

        {/* Right property panel */}
        <aside className="w-80 shrink-0 border-l border-slate-700 bg-slate-900 overflow-hidden flex flex-col">
          <NodePropertiesPanel node={selectedNode} onClose={() => setSelectedNode(null)} />
        </aside>
      </div>

      <style>{`
        @keyframes graphload {
          0% { background-position: 0% 50%; }
          100% { background-position: 100% 50%; }
        }
      `}</style>
    </div>
  );
}
