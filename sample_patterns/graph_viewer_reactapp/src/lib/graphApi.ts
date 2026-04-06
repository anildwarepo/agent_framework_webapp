// --- src/components/lib/graphApi.ts ---
export type RawItem = {
  id: string;
  label: string | null;        // e.g. "[\"Product\"]"
  properties: string | null;   // e.g. "{\"name\":\"Core\"}"
  kind?: string | null;        // e.g. "\"node\"" or "\"edge\""
  src?: string | null;
  dst?: string | null;
};

export type GraphNode = {
  id: string;
  label?: string;
  properties?: Record<string, any>;
  // force-graph runtime props
  x?: number; y?: number; vx?: number; vy?: number; fx?: number; fy?: number;
};

export type GraphLink = {
  id?: string;
  source: string;
  target: string;
  label?: string;
};

const API_BASE = "http://localhost:8080";

const safeJson = (s: any) => {
  if (s == null) return undefined;
  if (typeof s === "object") return s;
  try { return JSON.parse(String(s)); } catch { return undefined; }
};

const stripOuterQuotes = (s: any) => {
  if (s == null) return undefined;
  const t = String(s).trim();
  if (t.startsWith('"') && t.endsWith('"')) return t.slice(1, -1);
  return t;
};

const parseLabel = (raw: any): string | undefined => {
  if (!raw) return undefined;
  const t = String(raw).trim();
  try {
    const maybeArr = JSON.parse(t);
    if (Array.isArray(maybeArr) && maybeArr.length) return String(maybeArr[0]);
  } catch { /* ignore */ }
  return stripOuterQuotes(t);
};

function normalize(items: RawItem[]) {
  const nodes: GraphNode[] = [];
  const links: GraphLink[] = [];

  for (const it of items) {
    const kind = stripOuterQuotes(it.kind) ?? "";
    const label = parseLabel(it.label);
    const props = safeJson(it.properties);

    if (it.src && it.dst) {
      links.push({
        id: it.id,
        source: String(it.src),
        target: String(it.dst),
        label,
      });
    } else if (kind === "node" || (!it.src && !it.dst)) {
      nodes.push({ id: String(it.id), label, properties: props });
    }
  }
  return { nodes, links };
}

export async function fetchAll(): Promise<{ nodes: GraphNode[]; links: GraphLink[] }> {
  const res = await fetch(`${API_BASE}/nodes`);
  if (!res.ok) throw new Error(`Failed to load nodes: ${res.status}`);
  const data = (await res.json()) as RawItem[];
  return normalize(data);
}

export async function fetchRelated(labelOrType: string, id: string): Promise<GraphNode[]> {
  // Adjust this path/query to match your backend.
  const res = await fetch(
    `${API_BASE}/nodes/${encodeURIComponent(id)}/related?type=${encodeURIComponent(labelOrType)}`
  );
  if (!res.ok) throw new Error(`Failed to load related: ${res.status}`);
  const data = (await res.json()) as RawItem[];
  const { nodes } = normalize(data);
  return nodes;
}
