import { useEffect, useRef, useState } from "react";
import { Clipboard, Check, Maximize2, Minimize2, Terminal, X } from "lucide-react";
import type { McpLogEntry } from "./types";

interface McpLogPanelProps {
  logs: McpLogEntry[];
  isExpanded: boolean;
  onToggleExpand: () => void;
  onClear: () => void;
  onClose: () => void;
}

export default function McpLogPanel({
  logs,
  isExpanded,
  onToggleExpand,
  onClear,
  onClose,
}: McpLogPanelProps) {
  const [copied, setCopied] = useState(false);
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  function copyLogs() {
    const text = logs.map((l) => `${l.timestamp} [${l.level}] ${l.text}`).join("\n");
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

  return (
    <aside
      className={`${
        isExpanded ? "w-[50vw]" : "w-80 lg:w-96"
      } shrink-0 border-l border-white/[0.06] bg-gray-950 flex flex-col min-h-0 overflow-hidden transition-[width] duration-200`}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2.5 border-b border-white/[0.06] bg-gray-900/60">
        <div className="flex items-center gap-2">
          <Terminal className="h-4 w-4 text-emerald-400" />
          <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-300">
            MCP Server Logs
          </span>
          <span className="text-[10px] text-gray-600 font-mono">({logs.length})</span>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={copyLogs}
            className="text-gray-600 hover:text-gray-300 p-1 rounded-md hover:bg-white/[0.06] transition-colors"
            aria-label="Copy MCP logs to clipboard"
            title="Copy all logs"
          >
            {copied ? (
              <Check className="h-3.5 w-3.5 text-emerald-400" />
            ) : (
              <Clipboard className="h-3.5 w-3.5" />
            )}
          </button>
          <button
            type="button"
            onClick={onToggleExpand}
            className="text-gray-600 hover:text-gray-300 p-1 rounded-md hover:bg-white/[0.06] transition-colors"
            aria-label={isExpanded ? "Collapse MCP panel" : "Expand MCP panel"}
            title={isExpanded ? "Collapse" : "Expand"}
          >
            {isExpanded ? (
              <Minimize2 className="h-3.5 w-3.5" />
            ) : (
              <Maximize2 className="h-3.5 w-3.5" />
            )}
          </button>
          <button
            type="button"
            onClick={onClear}
            className="text-[10px] text-gray-600 hover:text-gray-300 px-1.5 py-0.5 rounded-md hover:bg-white/[0.06] transition-colors font-medium"
          >
            Clear
          </button>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-600 hover:text-gray-300 p-1 rounded-md hover:bg-white/[0.06] transition-colors"
            aria-label="Close MCP panel"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Log entries */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1 font-mono text-[12px] leading-relaxed">
        {logs.length === 0 ? (
          <div className="text-gray-700 text-center py-8 text-[11px]">
            MCP server processing logs will appear here...
          </div>
        ) : (
          logs.map((log) => <McpLogRow key={log.id} log={log} />)
        )}
        <div ref={endRef} />
      </div>
    </aside>
  );
}

function McpLogRow({ log }: { log: McpLogEntry }) {
  const toolMatch = log.text.match(/^\[([^\]]+)\]\s*(.*)$/s);
  const toolName = toolMatch ? toolMatch[1] : null;
  const body = toolMatch ? toolMatch[2] : log.text;
  const isSql = /\b(SELECT|MATCH|FROM|WHERE|RETURN|INSERT|UPDATE|DELETE)\b/i.test(body);

  return (
    <div
      className={`px-2 py-1.5 rounded-lg ${
        log.level === "error"
          ? "bg-red-500/10 text-red-300 border-l-2 border-red-500/60"
          : log.level === "warning"
          ? "bg-amber-500/10 text-amber-300 border-l-2 border-amber-500/60"
          : "bg-white/[0.02] text-gray-400 border-l-2 border-emerald-500/30"
      }`}
    >
      <div className="flex items-start gap-1.5">
        <span className="text-gray-600 text-[11px] shrink-0">{log.timestamp}</span>
        <div className="min-w-0">
          {toolName && (
            <span className="text-emerald-400 font-semibold text-[11px]">[{toolName}]</span>
          )}
          {isSql ? (
            <pre className="mt-0.5 whitespace-pre-wrap break-all text-teal-300/80 text-[11px] leading-snug">
              {body}
            </pre>
          ) : (
            <span className="ml-1">{body}</span>
          )}
        </div>
      </div>
    </div>
  );
}
