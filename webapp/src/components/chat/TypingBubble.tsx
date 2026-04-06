export default function TypingBubble() {
  return (
    <div className="flex w-full min-w-0 items-start gap-2">
      <div className="w-12 flex-shrink-0 flex justify-start">
        <div className="h-9 w-9 rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 shadow-lg shadow-indigo-500/20 flex items-center justify-center text-white text-xs font-semibold">
          AI
        </div>
      </div>
      <div className="inline-flex items-center gap-2 rounded-2xl px-4 py-2 bg-white/[0.05] text-gray-400 ring-1 ring-white/[0.06] shadow-sm">
        <span className="animate-pulse-fade">thinking...</span>
        <span className="typing-dots">
          <span className="dot" />
          <span className="dot" />
          <span className="dot" />
        </span>
      </div>
    </div>
  );
}
