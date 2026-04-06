import type { GraphData, RawItem, Node, Link } from "./types";
import { colorForLabel } from "./colors";

export function parseLabel(label?: string | null): string | undefined {
  if (!label) return undefined;
  try {
    const parsed = JSON.parse(label);
    if (Array.isArray(parsed) && parsed.length) return String(parsed[0]);
  } catch { /* noop */ }
  return label.replace(/^"+|"+$/g, "").replace(/^\[+"?|"+\]+$/g, "");
}

export function parseProps(props?: string | null): Record<string, any> {
  if (!props) return {};
  try { return JSON.parse(props); } catch { return {}; }
}

export function isEdgeLike(item: RawItem): boolean {
  const k = (item.kind ?? "").toLowerCase();
  return k.includes("edge") || (!!item.src && !!item.dst);
}

export function toGraph(items: RawItem[]): GraphData {
  const nodes = new Map<string, Node>();
  const links: Link[] = [];

  for (const it of items) {
    if (isEdgeLike(it)) {
      if (it.src && it.dst) links.push({ source: String(it.src), target: String(it.dst) });
      continue;
    }

    const group = parseLabel(it.label); // this is the "label" you want to key by
    const props = parseProps(it.properties);

    nodes.set(String(it.id), {
      id: String(it.id),
      group,
      color: colorForLabel(group ?? "Unknown"), // ← same label => same color
      name: props.name ?? props.id ?? String(it.id),
      mrr: typeof props.current_mrr === "number" ? props.current_mrr : undefined,
      raw: props,
    });
  }

  // Ensure endpoints exist as nodes
  for (const l of links) {
    const s = String(l.source), t = String(l.target);
    if (!nodes.has(s)) nodes.set(s, { id: s, group: undefined, color: colorForLabel("Unknown") });
    if (!nodes.has(t)) nodes.set(t, { id: t, group: undefined, color: colorForLabel("Unknown") });
  }

  return { nodes: Array.from(nodes.values()), links };
}
