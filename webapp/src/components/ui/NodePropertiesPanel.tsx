import { X } from "lucide-react";

type Node = { id: string; name?: string; group?: string; raw?: any; _isLabel?: boolean };

type Props = {
  node: Node | null;
  onClose: () => void;
};

/** Flatten nested objects into "key.subkey" entries for display */
function flattenProps(obj: Record<string, any>, prefix = ""): [string, string][] {
  const entries: [string, string][] = [];
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === "object" && !Array.isArray(v)) {
      entries.push(...flattenProps(v, key));
    } else if (Array.isArray(v)) {
      const display = v.length > 5
        ? `[${v.slice(0, 5).map(i => JSON.stringify(i)).join(", ")}, …+${v.length - 5}]`
        : JSON.stringify(v);
      entries.push([key, display]);
    } else {
      entries.push([key, String(v ?? "")]);
    }
  }
  return entries;
}

export default function NodePropertiesPanel({ node, onClose }: Props) {
  if (!node) {
    return (
      <div className="flex items-center justify-center h-full text-slate-500 text-sm px-4 text-center">
        Click a node to view its properties
      </div>
    );
  }

  const props = node.raw ? flattenProps(node.raw) : [];

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="shrink-0 flex items-center justify-between px-3 py-2 border-b border-slate-700">
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold text-sky-400 truncate">
            {node.name ?? node.id}
          </div>
          {node.group && (
            <div className="text-[11px] text-slate-400 mt-0.5">
              Label: <span className="text-slate-300">{node.group}</span>
            </div>
          )}
        </div>
        <button
          type="button"
          onClick={onClose}
          className="shrink-0 ml-2 text-slate-500 hover:text-slate-300 p-0.5 rounded hover:bg-slate-700 transition-colors"
          aria-label="Clear selection"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Properties */}
      <div className="flex-1 overflow-y-auto px-3 py-2">
        {props.length === 0 ? (
          <div className="text-slate-500 text-xs">No properties</div>
        ) : (
          <table className="w-full text-[12px] leading-relaxed">
            <tbody>
              {props.map(([k, v]) => (
                <tr key={k} className="border-b border-slate-800 last:border-0">
                  <td className="text-slate-400 pr-2 py-1 align-top whitespace-nowrap font-medium">
                    {k}
                  </td>
                  <td className="text-slate-200 py-1 align-top break-words max-w-[200px]">
                    {v.length > 200 ? v.slice(0, 200) + "…" : v}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Footer with node ID */}
      <div className="shrink-0 px-3 py-1.5 border-t border-slate-700 text-[10px] text-slate-500 font-mono truncate">
        ID: {node.id}
      </div>
    </div>
  );
}
