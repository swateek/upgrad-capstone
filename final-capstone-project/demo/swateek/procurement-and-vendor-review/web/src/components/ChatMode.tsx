"use client";

import {
  AssistantRuntimeProvider,
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  useLocalRuntime,
  type ChatModelAdapter,
} from "@assistant-ui/react";
import { useMemo, useState } from "react";
import type { ScoreSheet, ScreeningResult } from "@/lib/api";
import { ScoreSheetView, ScreeningCard } from "./results";
import { Badge, Callout } from "./ui";

// ---------------------------------------------------------------- stream protocol -----
type Progress = { type: string; t: number; role?: string; tool?: string; passed?: boolean;
  problems?: string[]; advisory?: string[]; rule?: string; reason?: string; summary?: string;
  what?: string; ok?: boolean };
type Final = {
  answer: string; citations: string[]; todos: { content: string; status: string }[];
  sources: { ref: string; citation: string; title: string; edition_date: string | null; synthetic: boolean }[];
  critic_passed: boolean; revisions: number; refusal_rules: string[]; steps: number;
  tool_calls: number; tokens: number; stopped: string | null; error: string | null;
  complete: boolean; partial: boolean; latency_s: number;
  payloads: { tool: string; ui_mode: string | null; result: unknown }[];
};
type TraceArgs = { events: Progress[]; final?: Final; error?: string };

async function* sse(body: ReadableStream<Uint8Array>) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return;
    buffer += decoder.decode(value, { stream: true });
    let cut;
    while ((cut = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 2);
      const event = /^event: (.*)$/m.exec(block)?.[1];
      const data = /^data: (.*)$/m.exec(block)?.[1];
      if (event && data) yield { event, data: JSON.parse(data) };
    }
  }
}

function traceCall(args: TraceArgs) {
  return { type: "tool-call" as const, toolCallId: "trace", toolName: "agent_trace",
    args: args as never, argsText: "", result: args.final ? "done" : undefined };
}

function makeAdapter(threadId: string): ChatModelAdapter {
  return {
    async *run({ messages, abortSignal }) {
      const last = messages[messages.length - 1];
      const text = last.content.map((p) => (p.type === "text" ? p.text : "")).join("");
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ thread_id: threadId, message: text }),
        signal: abortSignal,
      });
      if (!res.ok || !res.body) {
        const detail = await res.json().catch(() => ({}));
        yield { content: [{ type: "text", text: `Request failed: ${detail?.detail ?? res.status}` }] };
        return;
      }
      const events: Progress[] = [];
      for await (const { event, data } of sse(res.body)) {
        if (event === "progress") {
          events.push(data);
          yield { content: [traceCall({ events: [...events] })] };
        } else if (event === "final") {
          const final = data as Final;
          const parts = [
            traceCall({ events, final }),
            { type: "text" as const, text: final.answer || "No answer was produced." },
            ...final.payloads.map((p, i) => ({
              type: "tool-call" as const, toolCallId: `payload-${i}`, toolName: p.tool,
              args: {} as never, argsText: "", result: p.result,
            })),
          ];
          yield { content: parts };
        } else if (event === "error") {
          yield { content: [traceCall({ events, error: data.error }),
            { type: "text" as const, text: `The agent failed: ${data.error}` }] };
        }
      }
    },
  };
}

// ---------------------------------------------------------------- renderers -----------
const CITE = /\[([a-z0-9_]+:[^\]\s]+)\]/g;

function CitedText({ text }: { text: string }) {
  const parts: React.ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(CITE)) {
    parts.push(text.slice(last, m.index));
    parts.push(
      <span key={`${m[1]}-${m.index}`}
        className="mx-0.5 rounded bg-accent-soft px-1.5 py-0.5 font-mono text-[11px] text-accent">
        {m[1]}
      </span>,
    );
    last = (m.index ?? 0) + m[0].length;
  }
  parts.push(text.slice(last));
  return <p className="whitespace-pre-wrap leading-7">{parts}</p>;
}

const roleTone: Record<string, "accent" | "ok" | "neutral"> = { planner: "accent", executor: "ok" };

function Trace({ args }: { args: TraceArgs }) {
  const { events, final, error } = args;
  const running = !final && !error;
  const critic = events.filter((e) => e.type === "critic");
  return (
    <details open={running} className="mb-2 rounded-lg border border-line bg-bg text-xs">
      <summary className="flex cursor-pointer flex-wrap items-center gap-2 px-3 py-2">
        <span className="font-semibold">Agent trace</span>
        {running && <span className="h-3 w-3 animate-spin rounded-full border-2 border-line border-t-accent" />}
        {final && (
          <>
            <Badge tone={final.critic_passed ? "ok" : "warn"}>
              critic {final.critic_passed ? "passed" : "flagged"}{final.revisions ? ` · ${final.revisions} revision` : ""}
            </Badge>
            <span className="text-muted">
              {final.steps}/10 steps · {final.tool_calls} tool calls · {final.tokens.toLocaleString()} tokens · {final.latency_s}s
            </span>
            {final.refusal_rules.map((r) => <Badge key={r} tone="bad">{r}</Badge>)}
            {final.partial && <Badge tone="warn">incomplete: {final.stopped}</Badge>}
          </>
        )}
      </summary>
      <div className="space-y-2 border-t border-line px-3 py-2">
        {final && final.todos.length > 0 && (
          <div>
            <div className="mb-1 font-medium text-muted">Plan (planner)</div>
            <ol className="list-decimal pl-5">{final.todos.map((t, i) => <li key={i}>{t.content}</li>)}</ol>
          </div>
        )}
        <ol className="space-y-1">
          {events.map((e, i) => (
            <li key={i} className="flex flex-wrap items-center gap-2">
              <span className="w-10 text-right font-mono text-muted">{e.t.toFixed(1)}s</span>
              {e.type === "model_call" && <Badge tone={roleTone[e.role ?? ""] ?? "neutral"}>{e.role}</Badge>}
              {e.type === "tool_call" && <><Badge tone="neutral">tool</Badge><span className="font-mono">{e.tool}</span></>}
              {e.type === "tool_result" && <span className="text-muted">↳ {e.summary}</span>}
              {e.type === "critic" && (
                <><Badge tone={e.passed ? "ok" : "warn"}>critic {e.passed ? "pass" : "revise"}</Badge>
                  <span className="text-muted">{(e.problems ?? []).join(" · ")}</span></>
              )}
              {e.type === "refusal_rule" && <Badge tone="bad">refusal rule {e.rule}</Badge>}
              {e.type === "repaired" && <span className="text-muted">code repair: {e.what}</span>}
              {e.type === "stopped" && <Badge tone="warn">stopped: {e.reason}</Badge>}
              {["trimmed", "critic_skipped", "critic_error", "tool_refused", "error"].includes(e.type) && (
                <span className="text-warn">{e.type}: {e.reason ?? e.what ?? ""}</span>
              )}
            </li>
          ))}
        </ol>
        {critic.some((c) => (c.advisory ?? []).length > 0) && (
          <div className="text-muted">LLM critic notes (advisory): {critic.flatMap((c) => c.advisory ?? []).join(" · ")}</div>
        )}
        {final && final.sources.length > 0 && (
          <div>
            <div className="mb-1 font-medium text-muted">Retrieved sources</div>
            <ul className="space-y-0.5">
              {final.sources.map((s) => (
                <li key={s.ref}>
                  <span className={`font-mono ${final.citations.includes(s.citation) ? "text-accent" : "text-muted"}`}>
                    {s.citation}
                  </span>{" "}
                  {s.title}{s.synthetic ? " (synthetic)" : ""}{final.citations.includes(s.citation) ? " · cited" : ""}
                </li>
              ))}
            </ul>
          </div>
        )}
        {error && <Callout tone="bad">{error}</Callout>}
      </div>
    </details>
  );
}

function ToolResult({ toolName, result }: { toolName: string; result?: unknown }) {
  if (!result || typeof result !== "object" || "error" in (result as object)) return null;
  if (toolName === "score_bids") return <div className="mt-2"><ScoreSheetView sheet={result as ScoreSheet} detailed={false} /></div>;
  if (toolName === "screen_vendor") return <div className="mt-2"><ScreeningCard result={result as ScreeningResult} /></div>;
  return null;
}

// ---------------------------------------------------------------- thread UI -----------
function UserMessage() {
  return (
    <MessagePrimitive.Root className="flex justify-end">
      <div className="max-w-[80%] rounded-2xl bg-accent px-4 py-2 text-sm text-white dark:text-bg">
        <MessagePrimitive.Parts />
      </div>
    </MessagePrimitive.Root>
  );
}

function AssistantMessage() {
  return (
    <MessagePrimitive.Root className="rounded-xl border border-line bg-panel p-4 shadow-sm">
      <MessagePrimitive.Parts
        components={{
          Text: ({ text }) => <CitedText text={text} />,
          tools: {
            by_name: {
              agent_trace: ({ args }) => <Trace args={args as unknown as TraceArgs} />,
            },
            Fallback: ({ toolName, result }) => <ToolResult toolName={toolName} result={result} />,
          },
        }}
      />
    </MessagePrimitive.Root>
  );
}

const SUGGESTIONS = [
  "Up to what value can goods not on GeM be bought without quotations?",
  "Screen the firm DNS Overseas.",
  "Draft the score sheet for case_002.",
];

function Thread() {
  return (
    <ThreadPrimitive.Root className="relative z-10 flex h-[70vh] flex-col rounded-xl border border-line bg-bg">
      <ThreadPrimitive.Viewport className="flex-1 space-y-4 overflow-y-auto p-4">
        <ThreadPrimitive.Empty>
          <div className="mx-auto max-w-lg py-10 text-center">
            <p className="mb-4 text-sm text-muted">
              Ask about a rule, screen a firm, or draft a score sheet. The planner delegates to an executor,
              and a critic reviews every answer before you see it.
            </p>
            <div className="flex flex-col gap-2">
              {SUGGESTIONS.map((s) => (
                <ThreadPrimitive.Suggestion key={s} prompt={s} send
                  className="rounded-lg border border-line bg-panel px-3 py-2 text-left text-sm hover:border-accent">
                  {s}
                </ThreadPrimitive.Suggestion>
              ))}
            </div>
          </div>
        </ThreadPrimitive.Empty>
        <ThreadPrimitive.Messages components={{ UserMessage, AssistantMessage }} />
      </ThreadPrimitive.Viewport>
      <ComposerPrimitive.Root className="flex gap-2 border-t border-line bg-panel p-3">
        <ComposerPrimitive.Input
          autoFocus
          placeholder="Ask the procurement copilot…"
          className="flex-1 resize-none rounded-lg border border-line bg-bg px-3 py-2 text-sm outline-none focus:border-accent"
          rows={1}
        />
        <ComposerPrimitive.Send className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-white disabled:opacity-50 dark:text-bg">
          Send
        </ComposerPrimitive.Send>
      </ComposerPrimitive.Root>
    </ThreadPrimitive.Root>
  );
}

function newThreadId() {
  return `t-${crypto.randomUUID().replace(/-/g, "").slice(0, 16)}`;
}

function ChatRuntime({ threadId }: { threadId: string }) {
  const adapter = useMemo(() => makeAdapter(threadId), [threadId]);
  const runtime = useLocalRuntime(adapter);
  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <Thread />
    </AssistantRuntimeProvider>
  );
}

export function ChatMode() {
  const [threadId, setThreadId] = useState(newThreadId);
  return (
    <div className="space-y-3">
      <div className="relative z-10 flex items-center justify-between text-xs text-muted">
        <span>Conversation <span className="font-mono">{threadId}</span> · remembers the vendor and case you discuss</span>
        <button onClick={() => setThreadId(newThreadId())} className="rounded-lg border border-line bg-panel px-3 py-1 hover:border-accent">
          New conversation
        </button>
      </div>
      <ChatRuntime key={threadId} threadId={threadId} />
    </div>
  );
}
