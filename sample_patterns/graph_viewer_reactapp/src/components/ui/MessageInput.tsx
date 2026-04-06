import { useEffect, useRef, useState } from "react";

type Props = {
  onSend: (text: string) => void;
  disabled?: boolean;
};

export default function MessageInput({ onSend, disabled }: Props) {
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement | null>(null);

  function send() {
    const v = value.trim();
    if (!v || disabled) return;
    onSend(v);
    setValue("");
    ref.current?.focus();
  }

  useEffect(() => {
    ref.current?.focus();
  }, []);

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  return (
    <div className="input-bar">
      <textarea
        ref={ref}
        placeholder="Type a message…"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={onKeyDown}
        rows={1}
        className="text-input"
      />
      <button className="send-btn" onClick={send} disabled={disabled}>
        Send
      </button>
    </div>
  );
}
