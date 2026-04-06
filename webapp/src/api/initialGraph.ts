import { GraphAPI } from "./graph";
import { toGraph } from "@/graph/transform";
import type { GraphData } from "@/graph/types";

/** Cache by graph name to prevent dev StrictMode double fetch. */
const _cache = new Map<string, Promise<GraphData>>();

export function loadInitialGraph(graphName: string): Promise<GraphData> {
  if (!_cache.has(graphName)) {
    _cache.set(graphName, GraphAPI.initialGraph(graphName).then(items => toGraph(items)));
  }
  return _cache.get(graphName)!;
}

export function invalidateInitialGraph(graphName: string): void {
  _cache.delete(graphName);
}
