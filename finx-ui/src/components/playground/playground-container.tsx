"use client";

import { useState, useCallback, useRef } from "react";
import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import {
  Play,
  XCircle,
  Loader2,
  Sparkles,
  RotateCcw,
  Square,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { MarkdownContent } from "@/components/chat/markdown-content";

interface PlaygroundContainerProps {
  database: string;
}

interface HistoryEntry {
  id: string;
  query: string;
  response: string;
  timestamp: Date;
}

export function PlaygroundContainer({ database }: PlaygroundContainerProps) {
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const sessionIdRef = useRef<string | undefined>(undefined);

  const {
    messages,
    sendMessage,
    status,
    error: chatError,
    stop,
    setMessages,
  } = useChat({
    transport: new DefaultChatTransport({
      api: "/api/team-chat",
      body: () => ({
        session_id: sessionIdRef.current,
      }),
    }),
    onFinish: ({ message }) => {
      const content = message.parts
        .filter((p) => p.type === "text")
        .map((p) => ("text" in p ? p.text : ""))
        .join("");

      if (content) {
        setHistory((prev) => [
          {
            id: crypto.randomUUID(),
            query: query.trim(),
            response: content,
            timestamp: new Date(),
          },
          ...prev,
        ]);
      }

      // Extract session_id from data parts
      const sessionPart = message.parts.find((p) => p.type === "data-session");
      if (sessionPart && "data" in sessionPart) {
        const data = (sessionPart as { data: { session_id?: string } }).data;
        if (data.session_id) {
          sessionIdRef.current = data.session_id;
        }
      }
    },
    onData: (dataPart) => {
      if (!dataPart || typeof dataPart !== "object") return;
      const part = dataPart as Record<string, unknown>;
      if ("session_id" in part) {
        sessionIdRef.current = part.session_id as string;
      }
    },
    onError: (err) => {
      setError(err.message);
    },
  });

  const loading = status === "streaming" || status === "submitted";

  const handleGenerate = useCallback(async () => {
    if (!query.trim() || loading) return;
    setError(null);
    sendMessage({ text: query.trim() });
  }, [query, loading, sendMessage]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        handleGenerate();
      }
    },
    [handleGenerate]
  );

  const loadFromHistory = useCallback((entry: HistoryEntry) => {
    setQuery(entry.query);
    setError(null);
  }, []);

  const clearAll = useCallback(() => {
    setQuery("");
    setMessages([]);
    setError(null);
    sessionIdRef.current = undefined;
    textareaRef.current?.focus();
  }, [setMessages]);

  // Get the latest assistant response
  const latestResponse =
    messages.length > 0
      ? messages.filter((m) => m.role === "assistant").pop()
      : null;

  const latestContent =
    latestResponse?.parts
      .filter((p) => p.type === "text")
      .map((p) => ("text" in p ? p.text : ""))
      .join("") || null;

  return (
    <div className="flex h-full">
      <div className="flex flex-1 flex-col overflow-hidden">
        <div className="border-b border-border p-6">
          <div className="mx-auto max-w-4xl">
            <div className="flex items-center gap-2 mb-3">
              <Sparkles className="h-5 w-5 text-primary" />
              <h2 className="text-lg font-semibold">AI Playground</h2>
              <Badge variant="default" className="ml-2">
                {database}
              </Badge>
            </div>
            <p className="mb-4 text-sm text-muted-foreground">
              Ask questions in natural language and get answers from the AI agent
              team. Press{" "}
              <kbd className="rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-xs">
                Cmd Enter
              </kbd>{" "}
              to send.
            </p>
            <div className="relative">
              <Textarea
                ref={textareaRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="e.g. Show me all active branches with their total transaction amounts in the last 30 days"
                className="min-h-[100px] resize-none pr-24"
                disabled={loading}
              />
              <div className="absolute bottom-3 right-3 flex gap-2">
                {query && !loading && (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={clearAll}
                    className="h-8"
                  >
                    <RotateCcw className="h-3.5 w-3.5" />
                  </Button>
                )}
                {loading ? (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => stop()}
                    className="h-8 gap-1.5"
                  >
                    <Square className="h-3.5 w-3.5" />
                    Stop
                  </Button>
                ) : (
                  <Button
                    size="sm"
                    onClick={handleGenerate}
                    disabled={!query.trim()}
                    className="h-8 gap-1.5"
                  >
                    <Play className="h-3.5 w-3.5" />
                    Send
                  </Button>
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-auto p-6">
          <div className="mx-auto max-w-4xl space-y-4">
            {(error || chatError) && (
              <Card className="border-destructive/30 bg-destructive/5 p-4">
                <div className="flex items-start gap-3">
                  <XCircle className="mt-0.5 h-5 w-5 shrink-0 text-destructive" />
                  <div>
                    <p className="text-sm font-medium text-destructive">
                      Request Failed
                    </p>
                    <p className="mt-1 text-sm text-destructive/80">
                      {error || chatError?.message}
                    </p>
                  </div>
                </div>
              </Card>
            )}

            {loading && (
              <Card className="p-6">
                <div className="flex items-center gap-3">
                  <Loader2 className="h-5 w-5 animate-spin text-primary" />
                  <div>
                    <p className="text-sm font-medium">
                      Processing your query…
                    </p>
                    <p className="text-xs text-muted-foreground">
                      The agent team is working on your request
                    </p>
                  </div>
                </div>
              </Card>
            )}

            {latestContent && !loading && (
              <Card className="p-6">
                <MarkdownContent content={latestContent} />
              </Card>
            )}

            {!latestContent && !loading && !(error || chatError) && (
              <div className="flex flex-col items-center justify-center py-20 text-center">
                <div className="mb-4 rounded-full bg-muted p-4">
                  <Sparkles className="h-8 w-8 text-muted-foreground" />
                </div>
                <h3 className="text-sm font-medium">Ready to ask</h3>
                <p className="mt-1 max-w-sm text-xs text-muted-foreground">
                  Type a natural language question about your data and the AI
                  agent team will provide an answer.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="hidden w-72 flex-col border-l border-border bg-muted/20 lg:flex">
        <div className="border-b border-border px-4 py-3">
          <h3 className="text-sm font-medium">History</h3>
          <p className="text-xs text-muted-foreground">
            {history.length} queries
          </p>
        </div>
        <div className="flex-1 overflow-auto">
          {history.length === 0 && (
            <p className="px-4 py-8 text-center text-xs text-muted-foreground">
              No queries yet
            </p>
          )}
          {history.map((entry) => (
            <button
              key={entry.id}
              type="button"
              onClick={() => loadFromHistory(entry)}
              className="w-full border-b border-border/50 px-4 py-3 text-left transition-colors hover:bg-accent/50"
            >
              <p className="line-clamp-2 text-xs font-medium">{entry.query}</p>
              <div className="mt-1.5 flex items-center gap-2">
                <Badge variant="success" className="text-[10px]">
                  Done
                </Badge>
                <span className="text-[10px] text-muted-foreground">
                  {entry.timestamp.toLocaleTimeString()}
                </span>
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
