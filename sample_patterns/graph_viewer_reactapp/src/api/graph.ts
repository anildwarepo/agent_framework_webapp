import { API_BASE, fetchJson } from "./http";
import type { RawItem } from "@/graph/types";

export const GraphAPI = {
  initialGraph: () => fetchJson<RawItem[]>(`${API_BASE}/nodes`),
  nodeNeighborhood: (nodeId: string) =>
    fetchJson<RawItem[]>(`${API_BASE}/nodes/${encodeURIComponent(nodeId)}/all_edges`),
};
