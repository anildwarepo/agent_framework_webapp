import { GraphAPI } from "./graph";
import { toGraph } from "@/graph/transform";
import type { GraphData } from "@/graph/types";

/** Singleton to prevent dev StrictMode double fetch. */
let initialGraphPromise: Promise<GraphData> | null = null;

export function loadInitialGraph(): Promise<GraphData> {
  if (!initialGraphPromise) {
    initialGraphPromise = GraphAPI.initialGraph().then(items => toGraph(items));
  }
  return initialGraphPromise;
}
