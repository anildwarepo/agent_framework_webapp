import { useEffect, useRef, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { API } from "./api";
import GraphViewerDialog from "@/components/ui/GraphViewerDialog";
import {
  HeaderBar,
  ChatMessage,
  ComposerFooter,
  McpLogPanel,
  SettingsDialog,
  ElicitationDialog,
  TypingBubble,
} from "@/components/chat";
import type { McpLogEntry, ElicitationRequest, Message, AgentSetting, SelectOption } from "@/components/chat";

const MODE_OPTIONS: SelectOption[] = [
  { value: "graph", label: "Magentic Graph Search" },
];

const GRAPH_OPTIONS: SelectOption[] = [
  { value: "meetings_graph_v2", label: "meetings_graph_v2" },
  { value: "customer_graph", label: "customer_graph" },
  { value: "meetings_graph", label: "meetings_graph" },
];

const MODEL_OPTIONS = ["FW-GPT-OSS-120B", "gpt-4.1", "gpt-4.1-mini", "gpt-5.4-mini"];

/** Consume application/x-ndjson stream and emit parsed objects */
async function readNdjsonStream(
  body: ReadableStream<Uint8Array>,
  onEvent: (evt: any) => void
) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buf = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });

    let nl: number;
    while ((nl = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, nl).trim();
      buf = buf.slice(nl + 1);
      if (!line) continue;
      try {
        onEvent(JSON.parse(line));
      } catch (e) {
        console.warn("Bad NDJSON line:", line);
      }
    }
  }

  const leftover = buf.trim();
  if (leftover) {
    try { onEvent(JSON.parse(leftover)); } catch {}
  }
}

export default function ChatUI() {
  const [messages, setMessages] = useState<Message[]>(() => [
    { id: crypto.randomUUID(), role: "assistant", content: "Hi! How can I help you today?" },
  ]);
  const [mode, setMode] = useState(MODE_OPTIONS[0].value);
  const [selectedGraph, setSelectedGraph] = useState(GRAPH_OPTIONS[0].value);
  const [isTyping, setIsTyping] = useState(false);
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const [input, setInput] = useState("");
  const [user_id] = useState(() => crypto.randomUUID());
  const [progressPct, setProgressPct] = useState<number | null>(null);
  const [clientId, setClientId] = useState<string | null>(null);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [faqs, setFaqs] = useState<string[]>([]);
  const [selectedFaq, setSelectedFaq] = useState("");
  const [selectedModel, setSelectedModel] = useState("FW-GPT-OSS-120B");
  const [agentSettings, setAgentSettings] = useState<AgentSetting[]>([
    { id: crypto.randomUUID(), agent_name: "", agent_instructions: "" },
  ]);
  const controllerRef = useRef<AbortController | null>(null);
  const assistantIndexRef = useRef<number | null>(null);
  const [mcpLogs, setMcpLogs] = useState<McpLogEntry[]>([]);
  const [isMcpPanelOpen, setIsMcpPanelOpen] = useState(true);
  const [isMcpPanelExpanded, setIsMcpPanelExpanded] = useState(false);
  const [isGraphViewerOpen, setIsGraphViewerOpen] = useState(false);
  const [pendingElicitation, setPendingElicitation] = useState<ElicitationRequest | null>(null);

  // ─── Agent settings helpers ───
  function addAgentSetting() {
    setAgentSettings((prev) => [
      ...prev,
      { id: crypto.randomUUID(), agent_name: "", agent_instructions: "" },
    ]);
  }

  function updateAgentSetting(id: string, key: "agent_name" | "agent_instructions", value: string) {
    setAgentSettings((prev) =>
      prev.map((a) => (a.id === id ? { ...a, [key]: value } : a))
    );
  }

  // ─── Message mutation helpers ───
  function appendToAssistant(text: string) {
    setMessages((prev) => {
      const idx = assistantIndexRef.current ?? prev.length - 1;
      const msg = prev[idx];
      if (!msg || msg.role !== "assistant") return prev;
      const next = [...prev];
      next[idx] = { ...msg, content: msg.content + text, isTypingPlaceholder: false };
      return next;
    });
  }

  function appendToAssistantFinal(text: string) {
    setMessages((prev) => {
      const idx = assistantIndexRef.current ?? prev.length - 1;
      const msg = prev[idx];
      if (!msg || msg.role !== "assistant") return prev;
      const parts = msg.parts ?? { final: "", stream: "" };
      const nextFinal = (parts.final ?? "") + text;
      const next = [...prev];
      next[idx] = {
        ...msg,
        isTypingPlaceholder: false,
        parts: { ...parts, final: nextFinal },
        content: `${nextFinal}${parts.stream ?? ""}`,
      };
      return next;
    });
  }

  function appendToAssistantStream(text: string) {
    if (!text) return;
    setMessages((prev) => {
      const idx = assistantIndexRef.current ?? prev.length - 1;
      const msg = prev[idx];
      if (!msg || msg.role !== "assistant") return prev;
      const parts = msg.parts ?? { final: "", stream: "" };
      const nextStream = (parts.stream ?? "") + text;
      const next = [...prev];
      next[idx] = {
        ...msg,
        isTypingPlaceholder: false,
        parts: { ...parts, stream: nextStream },
        content: `${parts.final ?? ""}${nextStream}`,
      };
      return next;
    });
  }

  function toggleRunLog(id: string) {
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, isRunLogCollapsed: !m.isRunLogCollapsed } : m))
    );
  }

  function copyRunLog(stream: string) {
    navigator.clipboard.writeText(stream || "");
  }

  // ─── Scroll ───
  const scrollToBottom = () => {
    const el = viewportRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isTyping]);

  // ─── FAQ loader ───
  useEffect(() => {
    let mounted = true;
    setFaqs([]);
    setSelectedFaq("");

    (async () => {
      try {
        const res = await fetch(API.getFaqs(selectedGraph));
        if (!res.ok) { if (mounted) setFaqs([]); return; }
        const data = await res.json();
        const items = Array.isArray(data?.faqs)
          ? data.faqs.filter((item: unknown) => typeof item === "string")
          : [];
        if (mounted) { setFaqs(items); setSelectedFaq(""); }
      } catch {
        if (mounted) setFaqs([]);
      }
    })();

    return () => { mounted = false; };
  }, [selectedGraph]);

  // ─── SSE wire-up ───
  useEffect(() => {
    const es = new EventSource(`${API.sseEvents}?sid=${user_id}`);

    es.addEventListener("open", (e: MessageEvent) => {
      try { const { client_id } = JSON.parse(e.data ?? "{}"); setClientId(client_id ?? null); } catch {}
    });

    es.onmessage = (e: MessageEvent) => { console.log("SSE message:", e.data); };

    es.addEventListener("progress", (e: MessageEvent<string>) => {
      try {
        const msg = JSON.parse(e.data);
        const raw = msg?.progress ?? msg?.params?.progress;
        const pct = typeof raw === "number" ? Math.round(raw * 100)
          : Number.isFinite(Number(raw)) ? Math.round(Number(raw) * 100) : null;
        if (pct !== null) setProgressPct(pct);
      } catch (err) {
        console.error("Bad JSON in SSE progress event:", err, e.data);
      }
    });

    es.addEventListener("assistant", (e: MessageEvent) => {
      try {
        const root = JSON.parse(e.data);
        const level = root?.params?.level ?? "info";
        const texts: string[] = (root?.params?.data ?? [])
          .filter((d: any) => d?.type === "text" && typeof d?.text === "string")
          .map((d: any) => d.text);
        const text = texts.join(" ").trim() || "(message)";
        const prefix = level === "error" ? "❌ " : level === "warn" ? "⚠️ " : "";
        setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: "assistant", content: `${prefix}${text}` }]);
      } catch {}
    });

    es.addEventListener("mcplog", (e: MessageEvent) => {
      try {
        const root = JSON.parse(e.data);
        const level = root?.params?.level ?? "info";
        const text = root?.params?.text ?? "(log)";
        setMcpLogs((prev) => [...prev, { id: crypto.randomUUID(), timestamp: new Date().toLocaleTimeString(), level, text }]);
      } catch {}
    });

    es.addEventListener("elicitation", (e: MessageEvent) => {
      try {
        const root = JSON.parse(e.data);
        const params = root?.params;
        if (params?.elicitationId && params?.options?.length) {
          setPendingElicitation({
            elicitationId: params.elicitationId,
            message: params.message ?? "Please confirm",
            options: params.options,
            provided: params.provided ?? null,
          });
        }
      } catch {}
    });

    es.onerror = () => {};
    return () => es.close();
  }, [user_id]);

  // ─── Elicitation responder ───
  async function respondToElicitation(value: string | null) {
    const req = pendingElicitation;
    setPendingElicitation(null);
    if (!req) return;
    try {
      await fetch(API.elicitationRespond(req.elicitationId), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ value }),
      });
    } catch (err) {
      console.error("Elicitation respond failed:", err);
    }
  }

  // ─── Send handler ───
  const handleSendMessage = async (rawText: string) => {
    if (!rawText.trim() || isTyping) return;

    const text = rawText.trim();
    setInput("");
    setIsTyping(true);
    setProgressPct(0);
    setMcpLogs([]);

    setMessages((prev) => {
      const idx = prev.length + 1;
      assistantIndexRef.current = idx;
      return [
        ...prev,
        { id: crypto.randomUUID(), role: "user" as const, content: text },
        {
          id: crypto.randomUUID(),
          role: "assistant" as const,
          content: "",
          isTypingPlaceholder: true,
          isRunLogCollapsed: false,
          parts: { final: "", stream: "" },
        },
      ];
    });

    controllerRef.current?.abort();
    const ctrl = new AbortController();
    controllerRef.current = ctrl;

    try {
      const modeForApi = (mode || MODE_OPTIONS[0].value).toLowerCase();
      const res = await fetch(API.startConversation(user_id, modeForApi), {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/x-ndjson" },
        body: JSON.stringify({ user_query: text, client_id: clientId, graph_name: selectedGraph, model_name: selectedModel }),
        signal: ctrl.signal,
      });
      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

      setProgressPct((p) => (p === null ? 1 : Math.max(p, 1)));

      await readNdjsonStream(res.body, (obj) => {
        const payload = obj?.response_message ?? obj;
        const t = payload?.type as string | undefined;
        const delta = typeof payload?.delta === "string" ? payload.delta : "";
        const errorMessage = typeof payload?.message === "string" ? payload.message : "";

        if (!t) return;
        if (t === "WorkflowFinalResultEvent") {
          appendToAssistantFinal(delta);
        } else if (t === "error") {
          appendToAssistant(`⚠️ ${errorMessage || "Workflow failed."}`);
          setIsTyping(false);
          setProgressPct(null);
          return;
        } else if (t === "done") {
          setIsTyping(false);
          setProgressPct(null);
          return;
        } else {
          appendToAssistantStream(delta);
        }
        setProgressPct((p) => (p == null ? 5 : Math.min(p + 1, 95)));
      });

      setIsTyping(false);
      setProgressPct(null);
    } catch (err: any) {
      const msg = err?.name === "AbortError" ? "Request was canceled." : (err?.message ?? "Unknown error");
      appendToAssistant(`⚠️ Error fetching reply: ${msg}`);
      setIsTyping(false);
      setProgressPct(null);
    } finally {
      if (controllerRef.current === ctrl) controllerRef.current = null;
    }
  };

  const handleSend = () => handleSendMessage(input);

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleFaqSelect = async (faq: string) => {
    setSelectedFaq(faq);
    if (faq) {
      await handleSendMessage(faq);
      setSelectedFaq("");
    }
  };

  // ─── Render ───
  return (
    <div className="h-full w-full text-gray-200 flex flex-col overflow-hidden bg-gray-950">
      <HeaderBar
        userId={user_id}
        faqs={faqs}
        selectedFaq={selectedFaq}
        onFaqSelect={handleFaqSelect}
        selectedModel={selectedModel}
        onModelChange={setSelectedModel}
        modelOptions={MODEL_OPTIONS}
        selectedGraph={selectedGraph}
        onGraphChange={setSelectedGraph}
        graphOptions={GRAPH_OPTIONS}
        mode={mode}
        onModeChange={setMode}
        modeOptions={MODE_OPTIONS}
        isMcpPanelOpen={isMcpPanelOpen}
        onToggleMcpPanel={() => setIsMcpPanelOpen((v) => !v)}
        onOpenSettings={() => setIsSettingsOpen(true)}
        onOpenGraphViewer={() => setIsGraphViewerOpen(true)}
        isTyping={isTyping}
        progressPct={progressPct}
      />

      <div className="flex min-h-0 flex-1 w-full overflow-hidden">
        {/* Chat Panel */}
        <main className="min-h-0 min-w-0 flex-1 flex flex-col">
          <Card className="relative rounded-none border-0 bg-gray-950 shadow-none w-full flex-1 min-h-0 flex flex-col">
            <CardContent className="p-0 w-full flex-1 min-h-0">
              <ScrollArea className="h-full w-full" type="always">
                <div
                  className="p-2 space-y-2 w-full"
                  ref={(el) => {
                    if (!el) return;
                    setTimeout(() => {
                      const viewport = el.closest("[data-radix-scroll-area-viewport]") as HTMLDivElement | null;
                      if (viewport) viewportRef.current = viewport;
                    }, 0);
                  }}
                >
                  {messages.map((msg) => (
                    <ChatMessage
                      key={msg.id}
                      msg={msg}
                      onToggleRunLog={toggleRunLog}
                      onCopyRunLog={copyRunLog}
                    />
                  ))}
                  {isTyping && <TypingBubble />}
                </div>
              </ScrollArea>
            </CardContent>
          </Card>
        </main>

        {/* MCP Server Log Panel */}
        {isMcpPanelOpen && (
          <McpLogPanel
            logs={mcpLogs}
            isExpanded={isMcpPanelExpanded}
            onToggleExpand={() => setIsMcpPanelExpanded((v) => !v)}
            onClear={() => setMcpLogs([])}
            onClose={() => setIsMcpPanelOpen(false)}
          />
        )}
      </div>

      <ComposerFooter
        input={input}
        onInputChange={setInput}
        onSend={handleSend}
        onKeyDown={onKeyDown}
      />

      {isSettingsOpen && (
        <SettingsDialog
          agentSettings={agentSettings}
          onAddAgent={addAgentSetting}
          onUpdateAgent={updateAgentSetting}
          onClose={() => setIsSettingsOpen(false)}
        />
      )}

      <GraphViewerDialog open={isGraphViewerOpen} onClose={() => setIsGraphViewerOpen(false)} graphName={selectedGraph} />

      {pendingElicitation && (
        <ElicitationDialog
          request={pendingElicitation}
          onRespond={respondToElicitation}
        />
      )}
    </div>
  );
}
