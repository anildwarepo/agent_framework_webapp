import { fetchJson } from "./http";
import { API } from "@/api.tsx";
import type { RawItem } from "@/graph/types";

export type DiscoverLabel = {
  label: string;
  cnt: string | number;
  sample_payload: string;
};

export const GraphAPI = {
  discoverLabels: (graphName: string) =>
    fetchJson<DiscoverLabel[]>(API.graphDiscover(graphName)),
  initialGraph: (graphName: string) =>
    fetchJson<RawItem[]>(API.graphNodes(graphName)),
  nodesByLabel: (graphName: string, label: string, limit?: number) =>
    fetchJson<RawItem[]>(API.graphNodesByLabel(graphName, label, limit)),
  nodeNeighborhood: (graphName: string, nodeId: string) =>
    fetchJson<RawItem[]>(API.graphNodeNeighborhood(graphName, nodeId)),
};
