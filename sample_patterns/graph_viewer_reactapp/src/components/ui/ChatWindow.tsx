import { useEffect, useRef, useState } from "react";
import MessageList from "../ui/MessageList";
import MessageInput from "../ui/MessageInput";
import type { ChatMessage } from "../../types";
import { chatApi } from "../../services/chatApi";

export default function ChatWindow() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: crypto.randomUUID(),
      role: "user",
      text: "backup file testfile.txt on desltop-009 every 10 seconds",
      at: new Date().toISOString()
    },
    {
      id: crypto.randomUUID(),
      role: "server",
      text:
        "From MCP Server: Creating backup task: step 1 of 5 (session 61033cfb-7d49-40ca-9168-57a79d2f8533)",
      at: new Date().toISOString()
    },
    {
      id: crypto.randomUUID(),
      role: "server",
      text:
        "From MCP Server: Setting up backup task: step 2 of 5 (session 61033cfb-7d49-40ca-9168-57a79d2f8533)",
      at: new Date().toISOString()
    },
    {
      id: crypto.randomUUID(),
      role: "server",
      text:
        "Backup task for file 'testfile.txt' on server 'desltop-009' every 10 seconds has been successfully created, and the backup task agent has been set up for you.",
      at: new Date().toISOString()
    },
    {
      id: crypto.randomUUID(),
      role: "server",
      text:
        "From MCP Server: Initializing backup task: step 3 of 5 (session 61033cfb-7d49-40ca-9168-57a79d2f8533)",
      at: new Date().toISOString()
    },
    {
      id: crypto.randomUUID(),
      role: "server",
      text:
        "From MCP Server: Running backup task: step 4 of 5 (session 61033cfb-7d49-40ca-9168-57a79d2f8533)",
      at: new Date().toISOString()
    },
    {
      id: crypto.randomUUID(),
      role: "server",
      text:
        "From MCP Server: Backup completed: src: testfile.txt  dest: testfile.txt - 1d83a43d-1bff-42f6-9d5d-…",
      at: new Date().toISOString()
    }
  ]);

  const sendingRef = useRef(false);

  async function handleSend(text: string) {
    if (!text.trim() || sendingRef.current) return;

    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      text,
      at: new Date().toISOString()
    };
    setMessages((m) => [...m, userMsg]);

    // keep UI & API separated: delegate to chatApi
    sendingRef.current = true;
    for await (const serverChunk of chatApi.send(text)) {
      setMessages((m) => [
        ...m,
        {
          id: crypto.randomUUID(),
          role: "server",
          text: serverChunk,
          at: new Date().toISOString()
        }
      ]);
    }
    sendingRef.current = false;
  }

  return (
    <div className="chat-wrap">
      <header className="chat-header">
        <div className="title">MCP Console</div>
        <div className="subtitle">Secure agent control & logs</div>
      </header>

      <MessageList messages={messages} />

      <MessageInput onSend={handleSend} disabled={sendingRef.current} />
    </div>
  );
}
