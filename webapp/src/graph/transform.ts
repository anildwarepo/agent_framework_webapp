import type { GraphData, RawItem, Node, Link } from "./types";
import { colorForLabel } from "./colors";

/** Strip AGE agtype quoting: "\"value\"" → "value", "123" → "123" */
export function stripAgtype(val: unknown): string {
  if (val == null) return "";
  let s = String(val).trim();
  // Remove outer double-quotes that AGE wraps around agtype values
  while (s.length >= 2 && s.startsWith('"') && s.endsWith('"')) {
    s = s.slice(1, -1);
  }
  return s;
}

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
  const k = stripAgtype(item.kind).toLowerCase();
  return k === "edge" || (!!item.src && !!item.dst);
}

export function toGraph(items: RawItem[]): GraphData {
  const nodes = new Map<string, Node>();
  const links: Link[] = [];

  for (const it of items) {
    const id = stripAgtype(it.id);
    if (isEdgeLike(it)) {
      const src = stripAgtype(it.src);
      const dst = stripAgtype(it.dst);
      if (src && dst) links.push({ source: src, target: dst });
      continue;
    }

    const group = parseLabel(it.label);
    const props = parseProps(it.properties);

    nodes.set(id, {
      id,
      group,
      color: colorForLabel(group ?? "Unknown"),
      name: props.name ?? props.id ?? id,
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
