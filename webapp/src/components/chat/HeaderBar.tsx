import { Button } from "@/components/ui/button";
import { GitGraph, Settings, Terminal } from "lucide-react";
import type { SelectOption } from "./types";

interface HeaderBarProps {
  userId: string;
  faqs: string[];
  selectedFaq: string;
  onFaqSelect: (faq: string) => void;
  selectedModel: string;
  onModelChange: (model: string) => void;
  modelOptions: string[];
  selectedGraph: string;
  onGraphChange: (graph: string) => void;
  graphOptions: SelectOption[];
  mode: string;
  onModeChange: (mode: string) => void;
  modeOptions: SelectOption[];
  isMcpPanelOpen: boolean;
  onToggleMcpPanel: () => void;
  onOpenSettings: () => void;
  onOpenGraphViewer: () => void;
  isTyping: boolean;
  progressPct: number | null;
}

export default function HeaderBar({
  userId,
  faqs,
  selectedFaq,
  onFaqSelect,
  selectedModel,
  onModelChange,
  modelOptions,
  selectedGraph,
  onGraphChange,
  graphOptions,
  mode,
  onModeChange,
  modeOptions,
  isMcpPanelOpen,
  onToggleMcpPanel,
  onOpenSettings,
  onOpenGraphViewer,
  isTyping,
  progressPct,
}: HeaderBarProps) {
  return (
    <header className="shrink-0 z-20 border-b border-white/[0.06] bg-gray-900/80 backdrop-blur-xl w-full">
      <div className="px-4 py-2.5 flex flex-wrap items-center gap-2.5 w-full">
        <div className="text-xs text-gray-500 whitespace-nowrap shrink-0">
          User ID: <span className="font-mono text-gray-400">{userId}</span>
        </div>
        <Button
          type="button"
          variant="outline"
          className="h-8 rounded-lg border-white/[0.08] bg-white/[0.04] text-gray-300 hover:bg-white/[0.08] hover:text-gray-100 transition-colors"
          onClick={onOpenGraphViewer}
          aria-label="Visualize graph"
        >
          <GitGraph className="h-3.5 w-3.5" aria-hidden="true" />
          <span className="text-xs">Visualize Graph</span>
        </Button>
        <div className="flex flex-wrap items-center gap-2 ml-auto">
          <span className="text-[11px] text-gray-500 hidden sm:inline font-medium uppercase tracking-wider">FAQs</span>
          <select
            value={selectedFaq}
            onChange={(e) => onFaqSelect(e.target.value)}
            className="select-dark min-w-[10rem] max-w-[18rem] flex-shrink rounded-lg px-3 py-1.5 text-xs outline-none focus:ring-2 focus:ring-indigo-500/30"
            aria-label="FAQs"
            disabled={isTyping || faqs.length === 0}
          >
            <option value="">{faqs.length ? "Select FAQ" : "No FAQs available"}</option>
            {faqs.map((faq) => (
              <option key={faq} value={faq}>
                {faq}
              </option>
            ))}
          </select>
          <span className="text-[11px] text-gray-500 hidden sm:inline font-medium uppercase tracking-wider">Model</span>
          <select
            value={selectedModel}
            onChange={(e) => onModelChange(e.target.value)}
            className="select-dark min-w-[8rem] max-w-[11rem] flex-shrink rounded-lg px-3 py-1.5 text-xs outline-none focus:ring-2 focus:ring-indigo-500/30"
            aria-label="Model"
            disabled={isTyping}
          >
            {modelOptions.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
          <span className="text-[11px] text-gray-500 hidden sm:inline font-medium uppercase tracking-wider">Graph</span>
          <select
            value={selectedGraph}
            onChange={(e) => onGraphChange(e.target.value)}
            className="select-dark min-w-[8rem] max-w-[11rem] flex-shrink rounded-lg px-3 py-1.5 text-xs outline-none focus:ring-2 focus:ring-indigo-500/30"
            aria-label="Graph"
            disabled={isTyping}
          >
            {graphOptions.map((g) => (
              <option key={g.value} value={g.value}>
                {g.label}
              </option>
            ))}
          </select>
          <span className="text-[11px] text-gray-500 hidden sm:inline font-medium uppercase tracking-wider">Orchestration</span>
          <select
            value={mode}
            onChange={(e) => onModeChange(e.target.value)}
            className="select-dark min-w-[8rem] max-w-[11rem] flex-shrink rounded-lg px-3 py-1.5 text-xs outline-none focus:ring-2 focus:ring-indigo-500/30"
            aria-label="Orchestration"
          >
            {modeOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          <Button
            type="button"
            variant="outline"
            className="h-8 rounded-lg border-white/[0.08] bg-white/[0.04] text-gray-300 hover:bg-white/[0.08] hover:text-gray-100 transition-colors"
            onClick={onOpenSettings}
            aria-label="Open settings"
          >
            <Settings className="h-3.5 w-3.5" aria-hidden="true" />
            <span className="text-xs">Settings</span>
          </Button>
          <Button
            type="button"
            variant="outline"
            className={`h-8 rounded-lg border-white/[0.08] text-gray-300 hover:bg-white/[0.08] transition-colors ${
              isMcpPanelOpen ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400" : "bg-white/[0.04]"
            }`}
            onClick={onToggleMcpPanel}
            aria-label="Toggle MCP logs panel"
          >
            <Terminal className="h-3.5 w-3.5" aria-hidden="true" />
          </Button>
        </div>
      </div>
      {progressPct !== null && (
        <div className="h-0.5 bg-gray-800">
          <div
            className="h-0.5 w-0 transition-[width] duration-300 ease-out bg-gradient-to-r from-indigo-500 to-violet-500 rounded-full"
            style={{ width: `${Math.min(Math.max(progressPct, 0), 100)}%` }}
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={progressPct ?? 0}
          />
        </div>
      )}
    </header>
  );
}
