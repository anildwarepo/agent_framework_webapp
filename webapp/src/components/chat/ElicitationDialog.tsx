import type { ElicitationRequest } from "./types";

interface ElicitationDialogProps {
  request: ElicitationRequest;
  onRespond: (value: string | null) => void;
}

export default function ElicitationDialog({ request, onRespond }: ElicitationDialogProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-gray-900 border border-white/[0.08] rounded-2xl shadow-2xl p-6 w-full max-w-md mx-4">
        <h3 className="text-sm font-semibold text-gray-200 mb-1">MCP Server — Confirm Graph</h3>
        <p className="text-gray-500 text-xs mb-4">{request.message}</p>
        <div className="flex flex-col gap-2 mb-4">
          {request.options.map((opt) => (
            <button
              key={opt}
              onClick={() => onRespond(opt)}
              className={`w-full text-left px-4 py-2.5 rounded-xl border text-sm transition-all ${
                opt === request.provided
                  ? "border-indigo-500/50 bg-indigo-500/15 text-indigo-300 font-medium shadow-lg shadow-indigo-500/10"
                  : "border-white/[0.08] bg-white/[0.03] text-gray-300 hover:bg-white/[0.06] hover:border-white/[0.12]"
              }`}
            >
              {opt}
              {opt === request.provided && (
                <span className="ml-2 text-xs text-indigo-400">(provided)</span>
              )}
            </button>
          ))}
        </div>
        <button
          onClick={() => onRespond(null)}
          className="w-full text-center text-xs text-gray-600 hover:text-gray-400 py-1 transition-colors"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
