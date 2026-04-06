import { useEffect, useRef } from "react";
import MessageBubble from "../ui/MessageBubble";
import type { ChatMessage } from "../../types";

type Props = { messages: ChatMessage[] };

export default function MessageList({ messages }: Props) {
  const scrollerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    // always keep the latest message in view
    scrollerRef.current?.scrollTo({
      top: scrollerRef.current.scrollHeight,
      behavior: "smooth"
    });
  }, [messages]);

  return (
    <div className="messages" ref={scrollerRef}>
      {messages.map((m) => (
        <MessageBubble key={m.id} message={m} />
      ))}
    </div>
  );
}
