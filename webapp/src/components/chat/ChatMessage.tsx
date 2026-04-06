import { ChevronDown, Clipboard } from "lucide-react";
import { SafeHTML, sanitizeHtml, isHtml, hasTable } from "@/components/ui/safehtml";
import type { Message } from "./types";

interface ChatMessageProps {
  msg: Message;
  onToggleRunLog: (id: string) => void;
  onCopyRunLog: (stream: string) => void;
}

export default function ChatMessage({ msg, onToggleRunLog, onCopyRunLog }: ChatMessageProps) {
  const isUser = msg.role === "user";
  const clean = sanitizeHtml(msg.content);
  const tableMode = isHtml(clean) && hasTable(clean);
  const isEmptyAssistantPlaceholder = !isUser && msg.isTypingPlaceholder && !msg.content.trim();

  if (isEmptyAssistantPlaceholder) return null;

  return (
    <div className="flex w-full min-w-0 items-start gap-2">
      {/* Left avatar slot */}
      {!isUser && (
        <div className="w-12 flex-shrink-0 flex justify-start">
          <div className="h-9 w-9 rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 shadow-lg shadow-indigo-500/20 flex items-center justify-center text-white text-xs font-semibold">
            AI
          </div>
        </div>
      )}

      {/* Bubble column */}
      <div
        className={[
          "min-w-0 flex-1 flex",
          isUser ? "justify-end" : "justify-start",
        ].join(" ")}
      >
        <div
          className={[
            "relative isolate rounded-2xl px-4 py-3 shadow-md text-left",
            "inline-flex items-start min-w-0",
            isUser ? "max-w-[85vw] md:max-w-[88%]" : "max-w-full",
            isUser
              ? "bg-indigo-600/90 text-white ring-1 ring-indigo-500/20"
              : "bg-white/[0.05] text-gray-100 ring-1 ring-white/[0.06]",
          ].join(" ")}
        >
          {msg.parts ? (
            <SplitBubble msg={msg} onToggleRunLog={onToggleRunLog} onCopyRunLog={onCopyRunLog} />
          ) : tableMode ? (
            <TableBubble html={clean} />
          ) : (
            <div className="text-[15px] md:text-base leading-relaxed whitespace-pre-wrap break-words max-w-[70ch]">
              {isHtml(clean) ? <SafeHTML html={clean} /> : <span>{msg.content}</span>}
            </div>
          )}
        </div>
      </div>

      {/* Right avatar slot */}
      {isUser && (
        <div className="w-12 flex-shrink-0 flex justify-end">
          <div className="h-9 w-9 rounded-full bg-gradient-to-br from-sky-500 to-cyan-600 shadow-lg shadow-sky-500/20 flex items-center justify-center text-white text-xs font-semibold">
            You
          </div>
        </div>
      )}
    </div>
  );
}

function SplitBubble({
  msg,
  onToggleRunLog,
  onCopyRunLog,
}: {
  msg: Message;
  onToggleRunLog: (id: string) => void;
  onCopyRunLog: (stream: string) => void;
}) {
  const finalRaw = msg.parts!.final ?? "";
  const finalClean = sanitizeHtml(finalRaw);
  const finalHasTable = isHtml(finalClean) && hasTable(finalClean);

  return (
    <div className="w-full space-y-0">
      {/* Answer */}
      <div>
        <div className="text-[11px] uppercase tracking-wider text-indigo-400/80 mb-1 font-medium">Answer</div>
        {!finalRaw.trim() ? (
          <div className="opacity-70">…</div>
        ) : finalHasTable ? (
          <TableBubble html={finalClean} ariaLabel="Answer table" />
        ) : (
          <div className="text-[15px] md:text-base leading-relaxed whitespace-pre-wrap break-words max-w-[70ch]">
            {isHtml(finalClean) ? <SafeHTML html={finalClean} /> : <span>{finalRaw}</span>}
          </div>
        )}
      </div>

      {/* Run log */}
      <div className="mt-3">
        <button
          type="button"
          onClick={() => onToggleRunLog(msg.id)}
          className="group inline-flex items-center gap-2 text-left text-[12px] font-medium text-gray-500 hover:text-gray-300 transition-colors"
          aria-expanded={!msg.isRunLogCollapsed}
          aria-controls={`runlog-${msg.id}`}
        >
          <ChevronDown
            className={`h-4 w-4 transition-transform ${msg.isRunLogCollapsed ? "-rotate-90" : "rotate-0"}`}
            aria-hidden="true"
          />
          <span className="uppercase tracking-wider">Run log</span>
        </button>
        <button
          type="button"
          onClick={() => onCopyRunLog(msg.parts?.stream || "")}
          className="ml-2 text-gray-600 hover:text-gray-300 p-0.5 rounded hover:bg-white/[0.06] transition-colors"
          aria-label="Copy run log to clipboard"
          title="Copy run log"
        >
          <Clipboard className="h-3.5 w-3.5" />
        </button>

        <div id={`runlog-${msg.id}`} className="mt-2" hidden={!!msg.isRunLogCollapsed}>
          <div className="rounded-xl bg-gray-950/60 ring-1 ring-white/[0.06] p-3 overflow-x-auto">
            <pre className="whitespace-pre-wrap break-all font-mono text-[13px] leading-snug text-gray-400">
              {msg.parts!.stream || ""}
            </pre>
          </div>
        </div>
      </div>
    </div>
  );
}

function TableBubble({ html, ariaLabel = "Table content" }: { html: string; ariaLabel?: string }) {
  return (
    <div
      className="w-full max-w-full overflow-x-auto overscroll-x-contain pb-1"
      style={{ WebkitOverflowScrolling: "touch", scrollbarGutter: "stable" }}
      role="region"
      aria-label={ariaLabel}
    >
      <div
        className="
          inline-block w-max align-top
          [&_table]:w-max [&_table]:max-w-none [&_table]:min-w-[36rem]
          [&_thead_th]:text-left [&_thead_th]:font-semibold [&_thead_th]:px-3 [&_thead_th]:py-2
          [&_tbody_td]:px-3 [&_tbody_td]:py-2 [&_tbody_td]:align-top
          [&_td]:whitespace-nowrap
          [&_code]:break-all [&_a]:break-all
        "
      >
        <SafeHTML html={html} />
      </div>
    </div>
  );
}
