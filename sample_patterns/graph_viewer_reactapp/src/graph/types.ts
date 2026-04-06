export type RawItem = {
  id: string;
  label?: string | null;
  properties?: string | null;
  kind?: string | null;
  src?: string | null;
  dst?: string | null;
};

export type Node = {
  id: string;
  group?: string;
  color?: string;
  name?: string;
  mrr?: number;
  raw?: any;
};

export type Link = { source: string; target: string };

export type GraphData = { nodes: Node[]; links: Link[] };

export type NavLevel = {
  title: string;
  graph: GraphData;
  clickedNodeId?: string;
};
