import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { API } from "./api";
import { SafeHTML, sanitizeHtml, isHtml, hasTable } from "@/components/ui/safehtml";
import { ChevronDown } from "lucide-react";

interface Message {
  id: string; // NEW: stable key
  role: "user" | "assistant";
  content: string;
  parts?: {
    final: string;   // only MagenticFinalResultEvent
    stream: string;  // everything else
  };
  isTypingPlaceholder?: boolean;
  isRunLogCollapsed?: boolean; // NEW: collapsible state per message
}


function TypingBubble() {
  return (
    <div className="inline-flex items-center gap-2 rounded-2xl px-4 py-2 bg-white/10 text-slate-200 ring-1 ring-white/10 shadow-sm">
      <span className="opacity-80">Assistant is typing</span>
      <span className="typing-dots">
        <span className="dot" />
        <span className="dot" />
        <span className="dot" />
      </span>
    </div>
  );
}

export default function ChatUI() {
  const [messages, setMessages] = useState<Message[]>(() => [
    { id: crypto.randomUUID(), role: "assistant", content: "Hi! How can I help you today?" },
  ]);

  const [isTyping, setIsTyping] = useState(false);
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const [input, setInput] = useState("");
  const [user_id] = useState(() => crypto.randomUUID());
  const [progressPct, setProgressPct] = useState<number | null>(null);
  const [clientId, setClientId] = useState<string | null>(null);
  const taRef = useRef<HTMLTextAreaElement | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const assistantIndexRef = useRef<number | null>(null);

  function appendToAssistant(text: string) {
  setMessages(prev => {
    const idx = (assistantIndexRef.current ?? prev.length - 1);
    const msg = prev[idx];
    if (!msg || msg.role !== "assistant") return prev;
    const next = [...prev];
    next[idx] = { ...msg, content: msg.content + text, isTypingPlaceholder: false };
    return next;
  });
}

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

    // handle CRLF/LF and partial lines
    let nl: number;
    while ((nl = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, nl).trim();
      buf = buf.slice(nl + 1);
      if (!line) continue;
      try {
        onEvent(JSON.parse(line));
      } catch (e) {
        // If the backend ever logs non-JSON lines, just ignore them.
        console.warn("Bad NDJSON line:", line);
      }
    }
  }

  // flush any trailing line w/o newline
  const leftover = buf.trim();
  if (leftover) {
    try { onEvent(JSON.parse(leftover)); } catch {}
  }
}

function appendToAssistantFinal(text: string) {
  setMessages(prev => {
    const idx = (assistantIndexRef.current ?? prev.length - 1);
    const msg = prev[idx];
    if (!msg || msg.role !== "assistant") return prev;

    const parts = msg.parts ?? { final: "", stream: "" };
    const nextFinal = (parts.final ?? "") + text;

    const next = [...prev];
    next[idx] = {
      ...msg,
      isTypingPlaceholder: false,
      parts: { ...parts, final: nextFinal },
      // keep content as a simple concat for legacy render paths
      content: `${nextFinal}${parts.stream ?? ""}`,
    };
    return next;
  });
}

function appendToAssistantStream(text: string) {
  if (!text) return;
  setMessages(prev => {
    const idx = (assistantIndexRef.current ?? prev.length - 1);
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

  
  // smooth scroll to bottom on updates
  const scrollToBottom = () => {
    const el = viewportRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  };
  useEffect(() => {
    scrollToBottom();
  }, [messages, isTyping]);

  // autosize textarea
  const autosize = () => {
    const el = taRef.current;
    if (!el) return;
    el.style.height = "0px";
    el.style.height = Math.min(el.scrollHeight, 200) + "px";
  };
  useEffect(() => {
    autosize();
  }, [input]);

  // SSE wire-up
  useEffect(() => {
    const es = new EventSource(`${API.sseEvents}?sid=${user_id}`);

    es.addEventListener("open", (e: MessageEvent) => {
      try {
        const { client_id } = JSON.parse(e.data ?? "{}");
        setClientId(client_id ?? null);
      } catch {}
    });

    es.onmessage = (e: MessageEvent) => {
      console.log("SSE message:", e.data);
    };

    es.addEventListener("progress", (e: MessageEvent<string>) => {
      try {
        const msg = JSON.parse(e.data);
        const raw = msg?.progress ?? msg?.params?.progress;
        const pct =
          typeof raw === "number"
            ? Math.round(raw * 100)
            : Number.isFinite(Number(raw))
            ? Math.round(Number(raw) * 100)
            : null;
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
        setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: "assistant", content: `${prefix}${text}` },]);
      } catch {}
    });

    es.onerror = () => {};
    return () => es.close();
  }, [user_id]);

  function toggleRunLog(id: string) {
    setMessages(prev =>
      prev.map(m =>
        m.id === id ? { ...m, isRunLogCollapsed: !m.isRunLogCollapsed } : m
      )
    );
  }
  
  // send handler
  const handleSend = async () => {
  if (!input.trim() || isTyping) return;

  //const userMsg: Message = { id: crypto.randomUUID(), role: "user", content: input };
  const text = input; // snapshot before clearing
  setInput("");
  setIsTyping(true);
  setProgressPct(0);

  // Add user message + a placeholder assistant bubble
  setMessages(prev => {
    const idx = prev.length + 1; // user message + then assistant bubble
    assistantIndexRef.current = idx;
    return [
      ...prev,
      { id: crypto.randomUUID(), role: "user", content: text },
      {
        id: crypto.randomUUID(),
        role: "assistant",
        content: "",
        isTypingPlaceholder: true,
        isRunLogCollapsed: false,   // <-- default expanded
        parts: { final: "", stream: "" },
      },
    ];
  });

  

  // new request controller
  controllerRef.current?.abort();
  const ctrl = new AbortController();
  controllerRef.current = ctrl;

  try {
    const res = await fetch(API.startConversation(user_id), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Accept": "application/x-ndjson",
      },
      body: JSON.stringify({ user_query: text, client_id: clientId }),
      signal: ctrl.signal,
    });
    if (!res.ok || !res.body) {
      throw new Error(`HTTP ${res.status}`);
    }

    // optionally show "started"
    setProgressPct(p => (p === null ? 1 : Math.max(p, 1)));

    await readNdjsonStream(res.body, (obj) => {
      // New backend shape: {"response_message": {...}} plus a trailing {"response_message": {"type":"done", ...}}
      const payload = obj?.response_message ?? obj;
      const t = payload?.type as string | undefined;
      const delta = typeof payload?.delta === "string" ? payload.delta : "";

      if (!t) return;

      if (t === "MagenticFinalResultEvent") {
        appendToAssistantFinal(delta);
      } else if (t === "done") {
        setIsTyping(false);
        setProgressPct(null);
        return;
      } else {
        // Everything else goes into the Run log
        appendToAssistantStream(delta);
      }

      // keep the bar feeling alive
      setProgressPct((p) => (p == null ? 5 : Math.min(p + 1, 95)));
    });


    // If the stream ended without an explicit "done"
    setIsTyping(false);
    setProgressPct(null);
  } catch (err: any) {
    const msg = err?.name === "AbortError" ? "Request was canceled." : (err?.message ?? "Unknown error");
    // Replace the placeholder with the error text if it’s still there
    appendToAssistant(`⚠️ Error fetching reply: ${msg}`);
    setIsTyping(false);
    setProgressPct(null);
  } finally {
    if (controllerRef.current === ctrl) controllerRef.current = null;
  }
};


  // enter to send, shift+enter for newline
  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div
      className="
        min-h-dvh w-full text-slate-100
        bg-slate-950
        [background:radial-gradient(1000px_600px_at_20%_-20%,rgba(99,102,241,0.18),transparent),radial-gradient(1000px_600px_at_80%_120%,rgba(16,185,129,0.18),transparent)]
        grid grid-rows-[auto_1fr_auto]
      "
    >
      {/* Header */}
      <header className="sticky top-0 z-20 border-b border-white/10 bg-slate-900/60 backdrop-blur supports-[backdrop-filter]:bg-slate-900/60">
        <div className="max-w-5xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="h-7 w-7 rounded-xl bg-gradient-to-br from-fuchsia-500 to-indigo-500 shadow ring-1 ring-white/20" />
            <span className="font-semibold tracking-tight">MCP Server Reference App Demo</span>
          </div>
          <div className="text-xs text-slate-400">
            User ID: <span className="font-mono text-slate-200">{user_id}</span>
          </div>
        </div>
        {progressPct !== null && (
          <div className="h-1 bg-slate-800">
            <div
              className="h-1 w-0 transition-[width] duration-200 bg-gradient-to-r from-amber-400 via-fuchsia-400 to-indigo-400"
              style={{ width: `${Math.min(Math.max(progressPct, 0), 100)}%` }}
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={progressPct ?? 0}
            />
          </div>
        )}
      </header>

      {/* Chat Panel */}
      <main className="max-w-5xl mx-auto w-full px-4 py-6">
        <Card className="relative overflow-hidden rounded-3xl border border-white/10 bg-white/[0.06] shadow-2xl">
          <CardContent className="p-0">
            <ScrollArea className="h-[calc(100dvh-260px)] overflow-x-hidden">

              <div
                className="p-6 space-y-6"
                ref={(el) => {
                  if (!el) return;
                  setTimeout(() => {
                    const viewport = el.closest("[data-radix-scroll-area-viewport]") as HTMLDivElement | null;
                    if (viewport) viewportRef.current = viewport;
                  }, 0);
                }}
              >
                {messages.map((msg, idx) => {
                  const isUser = msg.role === "user";
                  const sideGap = isUser ? "mr-12" : "ml-12";
                  const clean = sanitizeHtml(msg.content);
                  const tableMode = isHtml(clean) && hasTable(clean);
                  const isEmptyAssistantPlaceholder = !isUser && msg.isTypingPlaceholder && !msg.content.trim();
                  if (isEmptyAssistantPlaceholder) {
                    // Don’t render a bubble yet; TypingBubble handles the UX.
                    return null;
                  }
                  return (
                    <div
                        key={msg.id}
                        className="flex w-full min-w-0 items-start gap-2 overflow-x-hidden" // ⬅️ important
                      >
                      {/* Left avatar slot (48px). Show only for assistant; keep spacer for user. */}
                      <div className="w-12 flex-shrink-0 flex justify-start">
                        {!isUser && (
                          <div className="h-9 w-9 rounded-full bg-gradient-to-br from-indigo-500 to-slate-600 ring-1 ring-white/10 shadow" />
                        )}
                      </div>

                      {/* Bubble column (shrinks safely) */}
                      <div
                          className={[
                            "min-w-0 flex-1 flex",                     // ⬅️ can shrink
                            isUser ? "justify-end" : "justify-start",
                          ].join(" ")}
                        >
                          <div
                            className={[
                              "relative isolate rounded-2xl px-4 py-3 shadow-lg ring-1 text-left",
                              "inline-flex items-start min-w-0",       // ⬅️ can shrink
                              "overflow-hidden",                       // ⬅️ bubble is the clip boundary
                              isUser ? "max-w-[85vw] md:max-w-[58%]" : "max-w-[90vw] md:max-w-[68%]",
                              isUser
                                ? "bg-gradient-to-br from-slate-600 to-slate-700 text-white ring-white/5"
                                : "bg-gradient-to-br from-indigo-600 to-slate-700 text-white ring-white/5",
                            ].join(" ")}
                          >


                            {msg.parts ? (
                              // ===== Split Assistant Bubble =====
                              <div className="w-full space-y-3">
                                {/* Answer (MagenticFinalResultEvent only) */}
                                <div>
                                  <div className="text-[11px] uppercase tracking-wide text-white/60 mb-1">Answer</div>
                                  {(() => {
                                    const finalRaw = msg.parts!.final ?? "";
                                    const finalClean = sanitizeHtml(finalRaw);
                                    const finalHasTable = isHtml(finalClean) && hasTable(finalClean);

                                    if (!finalRaw.trim()) {
                                      return <div className="opacity-70">…</div>;
                                    }

                                    return finalHasTable ? (
                                      <div
                                        className="w-full max-w-full overflow-x-auto overscroll-x-contain pb-1"
                                        style={{ WebkitOverflowScrolling: "touch", scrollbarGutter: "stable" }}
                                        role="region"
                                        aria-label="Answer table"
                                      >
                                        <div
                                          className="
                                            inline-block w-max align-top
                                            [&_table]:w-max [&_table]:max-w-none [&_table]:min-w-[36rem]
                                            [&_thead_th]:text-left [&_thead_th]:font-semibold [&_thead_th]:px-3 [&_thead_th]:py-2
                                            [&_tbody_td]:px-3 [&_tbody_td]:py-2 [&_tbody_td]:align-top
                                            [&_td]:whitespace-nowrap
                                            [&_code]:break-all [&_a]:break-all
                                          "
                                        >
                                          <SafeHTML html={finalClean} />
                                        </div>
                                      </div>
                                    ) : (
                                      <div className="text-[15px] md:text-base leading-relaxed whitespace-pre-wrap break-words max-w-[70ch]">
                                        {isHtml(finalClean) ? <SafeHTML html={finalClean} /> : <span>{finalRaw}</span>}
                                      </div>
                                    );
                                  })()}
                                </div>

                                {/* Run log (everything else) */}
                                <div className="border-t border-white/10 pt-2">
                                  <button
                                    type="button"
                                    onClick={() => toggleRunLog(msg.id)}
                                    className="group inline-flex items-center gap-2 text-left text-[12px] font-medium text-white/80 hover:text-white transition-colors"
                                    aria-expanded={!msg.isRunLogCollapsed}
                                    aria-controls={`runlog-${msg.id}`}
                                  >
                                    <ChevronDown
                                      className={`h-4 w-4 transition-transform ${msg.isRunLogCollapsed ? "-rotate-90" : "rotate-0"}`}
                                      aria-hidden="true"
                                    />
                                    <span className="uppercase tracking-wide">Run log</span>
                                  </button>

                                  <div
                                    id={`runlog-${msg.id}`}
                                    className="mt-2"
                                    hidden={!!msg.isRunLogCollapsed}
                                  >
                                    <pre className="whitespace-pre-wrap break-words font-mono text-[13px] leading-snug opacity-90">
                                      {msg.parts.stream || ""}
                                    </pre>
                                  </div>
                                </div>
                              </div>
                            ) : (
                              // ===== Legacy single-content bubble (unchanged) =====
                              tableMode ? (
                                <div
                                  className="w-full max-w-full overflow-x-auto overscroll-x-contain pb-1"
                                  style={{ WebkitOverflowScrolling: "touch", scrollbarGutter: "stable" }}
                                  role="region"
                                  aria-label="Table content"
                                >
                                  <div
                                    className="
                                      inline-block w-max align-top
                                      [&_table]:w-max [&_table]:max-w-none [&_table]:min-w-[36rem]
                                      [&_thead_th]:text-left [&_thead_th]:font-semibold [&_thead_th]:px-3 [&_thead_th]:py-2
                                      [&_tbody_td]:px-3 [&_tbody_td]:py-2 [&_tbody_td]:align-top
                                      [&_td]:whitespace-nowrap
                                      [&_code]:break-all [&_a]:break-all
                                    "
                                  >
                                    <SafeHTML html={clean} />
                                  </div>
                                </div>
                              ) : (
                                <div className="text-[15px] md:text-base leading-relaxed whitespace-pre-wrap break-words max-w-[70ch]">
                                  {isHtml(clean) ? <SafeHTML html={clean} /> : <span>{msg.content}</span>}
                                </div>
                              )
                            )}




                          </div>
                        </div>


                      {/* Right avatar slot (48px). Show only for user; keep spacer for assistant. */}
                      <div className="w-12 flex-shrink-0 flex justify-end">
                        {isUser && (
                          <div className="h-9 w-9 rounded-full bg-gradient-to-br from-slate-500 to-slate-700 ring-1 ring-white/10 shadow" />
                        )}
                      </div>
                    </div>
                  );


                })}

                {/* Typing indicator (outside the array so it never replaces messages) */}
                {isTyping && (
                  <div className="flex justify-start">
                    <TypingBubble />
                  </div>
                )}
              </div>
            </ScrollArea>
          </CardContent>
        </Card>
      </main>

      {/* Composer */}
      <footer className="border-t border-white/10 bg-slate-900/50 backdrop-blur supports-[backdrop-filter]:bg-slate-900/50 mb-6 md:mb-10 pb-[max(0.5rem,env(safe-area-inset-bottom))]">
        <div className="max-w-5xl mx-auto px-4 py-4">
          <div className="rounded-2xl border border-white/10 bg-white/5 p-2 shadow-xl flex items-end gap-2">
            <textarea
              ref={taRef}
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="Type a message…"
              className="flex-1 resize-none bg-transparent outline-none text-slate-100 placeholder:text-slate-400 px-3 py-2 rounded-xl leading-6"
              aria-label="Message"
            />
            <Button
              onClick={handleSend}
              className="rounded-xl px-5 py-2.5 font-medium bg-gradient-to-br from-fuchsia-500 to-indigo-600 text-white hover:from-fuchsia-400 hover:to-indigo-500 shadow-lg shadow-indigo-900/30"
            >
              Send
            </Button>
          </div>
        </div>
      </footer>
    </div>
  );
}
