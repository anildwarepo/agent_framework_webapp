import { useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";

interface ComposerFooterProps {
  input: string;
  onInputChange: (value: string) => void;
  onSend: () => void;
  onKeyDown: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void;
}

export default function ComposerFooter({ input, onInputChange, onSend, onKeyDown }: ComposerFooterProps) {
  const taRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    const el = taRef.current;
    if (!el) return;
    el.style.height = "0px";
    el.style.height = Math.min(el.scrollHeight, 200) + "px";
  }, [input]);

  return (
    <footer className="shrink-0 border-t border-white/[0.06] bg-gray-900/80 backdrop-blur-xl pb-[env(safe-area-inset-bottom)]">
      <div className="px-4 py-3">
        <div className="rounded-2xl border border-white/[0.08] bg-white/[0.03] p-2 shadow-lg flex items-end gap-2">
          <textarea
            ref={taRef}
            rows={1}
            value={input}
            onChange={(e) => onInputChange(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Type a message…"
            className="flex-1 resize-none bg-transparent outline-none text-gray-100 placeholder:text-gray-500 px-3 py-2 rounded-xl leading-6"
            aria-label="Message"
          />
          <Button
            onClick={onSend}
            className="rounded-xl px-5 py-2.5 font-medium bg-gradient-to-r from-indigo-500 to-violet-600 text-white hover:from-indigo-400 hover:to-violet-500 shadow-lg shadow-indigo-500/20 transition-all"
          >
            Send
          </Button>
        </div>
      </div>
    </footer>
  );
}
