import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { AgentSetting } from "./types";

interface SettingsDialogProps {
  agentSettings: AgentSetting[];
  onAddAgent: () => void;
  onUpdateAgent: (id: string, key: "agent_name" | "agent_instructions", value: string) => void;
  onClose: () => void;
}

export default function SettingsDialog({
  agentSettings,
  onAddAgent,
  onUpdateAgent,
  onClose,
}: SettingsDialogProps) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Agent settings"
    >
      <div className="w-full max-w-3xl rounded-2xl border border-white/[0.08] bg-gray-900 shadow-2xl">
        <div className="flex items-center justify-between border-b border-white/[0.06] px-5 py-4">
          <h2 className="text-base font-semibold text-gray-100">Agent Settings</h2>
          <Button
            type="button"
            variant="ghost"
            className="text-gray-500 hover:text-gray-100"
            onClick={onClose}
          >
            Close
          </Button>
        </div>

        <div className="max-h-[70vh] overflow-y-auto px-5 py-4 space-y-4">
          {agentSettings.map((agent, index) => (
            <div key={agent.id} className="rounded-xl border border-white/[0.06] bg-white/[0.03] p-4 space-y-3">
              <div className="text-[11px] uppercase tracking-wider text-indigo-400/80 font-medium">Agent {index + 1}</div>
              <div className="space-y-1">
                <label className="text-xs text-gray-400">Agent Name</label>
                <Input
                  value={agent.agent_name}
                  onChange={(e) => onUpdateAgent(agent.id, "agent_name", e.target.value)}
                  placeholder="Enter agent name"
                  className="bg-white/[0.04] border-white/[0.08] text-gray-100 focus:border-indigo-500/50"
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-gray-400">Agent Instructions</label>
                <textarea
                  value={agent.agent_instructions}
                  onChange={(e) => onUpdateAgent(agent.id, "agent_instructions", e.target.value)}
                  placeholder="Enter agent instructions"
                  rows={4}
                  className="w-full resize-y rounded-md border border-white/[0.08] bg-white/[0.04] px-3 py-2 text-sm text-gray-100 outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/30 focus-visible:border-indigo-500/50"
                />
              </div>
            </div>
          ))}
        </div>

        <div className="flex items-center justify-between border-t border-white/[0.06] px-5 py-4">
          <Button
            type="button"
            onClick={onAddAgent}
            className="rounded-lg bg-gradient-to-r from-indigo-500 to-violet-600 text-white hover:from-indigo-400 hover:to-violet-500 shadow-lg shadow-indigo-500/20"
          >
            Add Agent
          </Button>
          <Button
            type="button"
            variant="outline"
            className="border-white/[0.08] bg-white/[0.04] text-gray-300 hover:bg-white/[0.08]"
            onClick={onClose}
          >
            Done
          </Button>
        </div>
      </div>
    </div>
  );
}
