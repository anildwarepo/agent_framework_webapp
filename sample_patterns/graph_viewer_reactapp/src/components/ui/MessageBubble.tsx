import type { ChatMessage } from "../../types";

export default function MessageBubble({ message }: { message: ChatMessage }) {
  const mine = message.role === "user";

  return (
    <div className={`row ${mine ? "mine" : "theirs"}`}>
      {!mine && (
        <div className="avatar" aria-hidden>
          <div className="dot" />
        </div>
      )}

      <div className={`bubble ${mine ? "bubble-mine" : "bubble-theirs"}`}>
        <p className="bubble-text">{message.text}</p>
      </div>
    </div>
  );
}
