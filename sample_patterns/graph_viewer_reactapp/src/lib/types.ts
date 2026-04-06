// --- src/types.ts ---
export type ApiNode = {
  id: string;
  label: string; // JSON string of ["LabelName"]
  properties: string | null; // JSON string or null
  kind: string; // JSON string like "\"node\"" or "\"edge\""
  src?: string | null;
  dst?: string | null;
};

export type GraphNode = {
  id: string;
  label: string; // e.g. Product, Customer
  props?: Record<string, any> | null;
};

export type GraphLink = {
  id: string;
  source: string; // node id
  target: string; // node id
  label: string; // e.g. ADOPTED_PRODUCT
};

