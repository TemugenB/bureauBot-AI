import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowLeft, Bot, Flag, User, Coffee, Send, ChevronDown, ChevronRight, ExternalLink } from "lucide-react";
import { Container } from "@/components/Container";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FlagMessageDialog } from "@/components/FlagMessageDialog";
import { streamChat, CitationInfo } from "@/lib/api";
import { cn } from "@/lib/utils";

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  rawContent: string;
  flagged?: boolean;
  sources?: CitationInfo[];
  error?: string;
  disclaimer?: string;
};

function stripCitations(text: string): string {
  return text.replace(/\[SRC:[^\]]+\]/g, "").trim();
}

export function ChatPage() {
  const [searchParams] = useSearchParams();
  const topic = searchParams.get("topic");
  const q = searchParams.get("q");

  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [streaming, setStreaming] = useState(false);
  const [turnIndex, setTurnIndex] = useState(0);
  const bottomRef = useRef<HTMLDivElement>(null);
  const initialized = useRef(false);

  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;
    if (q) sendMessage(q);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = async (text: string) => {
    const currentTurn = turnIndex;
    const userMsg: Message = { id: `u-${currentTurn}`, role: "user", content: text, rawContent: text };
    const assistantMsg: Message = { id: `a-${currentTurn}`, role: "assistant", content: "", rawContent: "" };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setStreaming(true);
    setTurnIndex((i) => i + 1);

    try {
      for await (const event of streamChat(text, sessionId)) {
        if (event.type === "session") {
          setSessionId(event.data as string);
        } else if (event.type === "token") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsg.id
                ? { ...m, rawContent: m.rawContent + (event.data as string), content: stripCitations(m.rawContent + (event.data as string)) }
                : m,
            ),
          );
          await new Promise((r) => setTimeout(r, 0));
        } else if (event.type === "error") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsg.id
                ? { ...m, error: event.data as string, content: m.content || "An error occurred." }
                : m,
            ),
          );
        } else if (event.type === "disclaimer") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsg.id ? { ...m, disclaimer: event.data as string } : m,
            ),
          );
        } else if (event.type === "citations") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsg.id ? { ...m, sources: event.data as CitationInfo[] } : m,
            ),
          );
        } else if (event.type === "done") {
          // streaming complete
        }
      }
    } catch {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantMsg.id ? { ...m, content: m.content || "An error occurred. Please try again." } : m,
        ),
      );
    }
    setStreaming(false);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || streaming) return;
    setInput("");
    sendMessage(text);
  };

  const markFlagged = (id: string) => {
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, flagged: true } : m)));
  };

  return (
    <Container className="flex flex-col py-8 sm:py-12" style={{ height: "calc(100vh - 4rem)" }}>
      <Link to="/" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground">
        <ArrowLeft className="h-4 w-4" /> Back
      </Link>

      <div className="mt-4 flex items-center gap-2">
        <Coffee className="h-5 w-5 text-primary" />
        <h1 className="text-2xl font-bold tracking-tight text-foreground">
          {topic || "Conversation"}
        </h1>
      </div>

      <div className="mt-6 flex-1 space-y-6 overflow-y-auto">
        {messages.map((m) => (
          <MessageBubble key={m.id} message={m} sessionId={sessionId ?? ""} turnIndex={turnIndex} onFlagged={() => markFlagged(m.id)} />
        ))}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={handleSubmit} className="mt-4 flex gap-2">
        <Input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Type your question..." className="h-12 text-base" disabled={streaming} />
        <Button type="submit" size="lg" className="h-12" disabled={streaming || !input.trim()}>
          <Send className="h-4 w-4" />
        </Button>
      </form>
    </Container>
  );
}

function CitationCard({ citation }: { citation: CitationInfo }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="rounded border border-border bg-muted/30 px-3 py-2">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2 text-left text-xs"
      >
        {expanded ? <ChevronDown className="h-3 w-3 shrink-0" /> : <ChevronRight className="h-3 w-3 shrink-0" />}
        <span className="font-medium text-foreground">📄 {citation.doc_title}{citation.section_title && ` → ${citation.section_title}`}</span>
        {citation.source_url && (
          <a
            href={citation.source_url}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="ml-auto text-primary hover:text-primary/80"
            aria-label="Open source"
          >
            <ExternalLink className="h-3 w-3" />
          </a>
        )}
      </button>
      {expanded && (
        <p className="mt-2 text-xs text-muted-foreground leading-relaxed">{citation.excerpt}</p>
      )}
    </div>
  );
}

function MessageBubble({ message, sessionId, turnIndex, onFlagged }: { message: Message; sessionId: string; turnIndex: number; onFlagged: () => void }) {
  const [flagOpen, setFlagOpen] = useState(false);
  const isUser = message.role === "user";

  return (
    <div className={cn("flex gap-3", isUser ? "flex-row-reverse" : "flex-row")}>
      <div className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-full", isUser ? "bg-accent text-accent-foreground" : "bg-primary text-primary-foreground")}>
        {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </div>

      <div className={cn("flex max-w-[85%] flex-col gap-1", isUser && "items-end")}>
        <div className={cn("rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm whitespace-pre-wrap", isUser ? "rounded-tr-sm bg-primary text-primary-foreground" : "rounded-tl-sm border border-border bg-card text-card-foreground")}>
          {message.content || <span className="animate-pulse">Thinking...</span>}
        </div>

        {!isUser && message.error && (
          <div className="mt-1 rounded-md border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300">
            ⚠ {message.error}
          </div>
        )}

        {!isUser && message.disclaimer && (
          <div className="mt-1 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-700 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-300">
            ⚠ {message.disclaimer}
          </div>
        )}

        {!isUser && message.sources && message.sources.length > 0 && (
          <div className="mt-1 space-y-1.5">
            <span className="text-xs font-medium text-muted-foreground">Sources:</span>
            {message.sources.map((s, i) => (
              <CitationCard key={i} citation={s} />
            ))}
          </div>
        )}

        {!isUser && (
          <>
            <Button type="button" variant="ghost" size="sm" onClick={() => !message.flagged && setFlagOpen(true)} disabled={message.flagged}
              className={cn("h-7 gap-1.5 px-2 text-xs", message.flagged ? "text-primary" : "text-muted-foreground hover:text-foreground")}>
              <Flag className={cn("h-3.5 w-3.5", message.flagged && "fill-primary")} />
              {message.flagged ? "Reported" : "Report"}
            </Button>
            <FlagMessageDialog open={flagOpen} onOpenChange={setFlagOpen} sessionId={sessionId} turnId={turnIndex} onFlagged={onFlagged} />
          </>
        )}
      </div>
    </div>
  );
}
