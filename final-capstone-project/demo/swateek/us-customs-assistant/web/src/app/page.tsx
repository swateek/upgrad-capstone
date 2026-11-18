"use client";

import { useEffect, useRef, useState } from "react";
import { AnswerCard } from "@/components/AnswerCard";
import { ClarifyCard } from "@/components/ClarifyCard";
import type { FactEdits } from "@/components/FactsEditor";
import { Progress, type ProgressState } from "@/components/Progress";
import { ApiError, getHealth, getThread, stream, type Card, type Facts } from "@/lib/api";

// Ask -> (Clarify) -> Answer card, in one conversation thread (plan §9). Follow-ups and
// corrections go to the same thread; editing the facts on the card replans.

const EXAMPLES = [
  "Back from 10 days in Italy with four bottles of wine, 750 ml each, $30 a bottle. Do I owe anything?",
  "Coming home from Cancún. I bought a box of 25 Cuban cigars and a bottle of Cuban rum there. Is that fine?",
  "Flying home from Dubai after two weeks. I'm 45 and haven't used my exemption this month. I bought two cartons of cigarettes (400) at duty-free.",
  "Day trip to Tijuana. I'm 30 and it's my first trip this month. I bought one 750 ml bottle of tequila for $40.",
];

type Turn = { id: number; role: "user"; text: string } | { id: number; role: "assistant"; card: Card };

function describeEdits(e: FactEdits): string {
  const parts = [
    ...Object.entries(e.profile).map(([k, v]) => `${k.replaceAll("_", " ")}: ${String(v)}`),
    ...Object.entries(e.lines).flatMap(([n, fields]) =>
      Object.entries(fields).map(([k, v]) => `item ${n} ${k.replaceAll("_", " ")}: ${String(v)}`),
    ),
  ];
  return `Edited the facts: ${parts.join("; ")}`;
}

export default function Home() {
  const [question, setQuestion] = useState("");
  const [threadId, setThreadId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [progress, setProgress] = useState<ProgressState | null>(null);
  const [facts, setFacts] = useState<Facts | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [apiNote, setApiNote] = useState<string>("checking…");
  const nextId = useRef(1);
  const bottom = useRef<HTMLDivElement>(null);
  const busy = progress !== null;

  useEffect(() => {
    getHealth()
      .then((h) => setApiNote(`${h.mode} mode · agent ${h.agent ?? "ready"}`))
      .catch(() => setApiNote("the API is not reachable"));
  }, []);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns, progress]);

  async function run(path: string, body: unknown, shown: string) {
    setError(null);
    setTurns((t) => [...t, { id: nextId.current++, role: "user", text: shown }]);
    setProgress({ queued: false, steps: [] });
    try {
      await stream(path, body, (e) => {
        if (e.event === "queued") setProgress((p) => ({ queued: true, steps: p?.steps ?? [] }));
        if (e.event === "node")
          setProgress((p) => (p && p.steps.at(-1) === e.label ? p : { queued: false, steps: [...(p?.steps ?? []), e.label] }));
        if (e.event === "error") setError(e.detail);
        if (e.event === "card") {
          setThreadId(e.thread_id);
          setTurns((t) => [...t, { id: nextId.current++, role: "assistant", card: e.card }]);
          getThread(e.thread_id)
            .then((th) => setFacts(th?.facts ?? null))
            .catch(() => setFacts(null));
        }
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The API is not reachable.");
    } finally {
      setProgress(null);
    }
  }

  function ask(text: string) {
    const q = text.trim();
    if (!q || busy) return;
    setQuestion("");
    void run("chat", threadId ? { message: q, thread_id: threadId } : { message: q }, q);
  }

  function edit(e: FactEdits) {
    if (!threadId || busy) return;
    void run(`threads/${threadId}/facts`, e, describeEdits(e));
  }

  function reset() {
    setThreadId(null);
    setTurns([]);
    setFacts(null);
    setError(null);
    setQuestion("");
  }

  const lastAssistant = [...turns].reverse().find((t) => t.role === "assistant")?.id;
  const started = turns.length > 0;

  const composer = (
    <form
      className="rounded-2xl border border-line bg-surface p-3 shadow-[0_1px_2px_rgba(0,0,0,0.04)] transition focus-within:border-accent"
      onSubmit={(e) => {
        e.preventDefault();
        ask(question);
      }}
    >
      <label htmlFor="question" className="sr-only">
        Your question
      </label>
      <textarea
        id="question"
        rows={started ? 2 : 3}
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            ask(question);
          }
        }}
        placeholder={
          started
            ? "Reply, or correct a fact (e.g. “actually I was away 3 days”)"
            : "e.g. Two bottles of whisky from Scotland after a week away"
        }
        className="w-full resize-none bg-transparent px-2 py-1.5 text-base leading-relaxed outline-none placeholder:text-muted/70"
      />
      <div className="flex items-center justify-between gap-3 px-2 pt-1">
        <span className="text-xs text-muted">Answers are estimates. Declare everything you bring.</span>
        <button
          type="submit"
          disabled={!question.trim() || busy}
          className="rounded-full bg-ink px-4 py-1.5 text-sm font-medium text-bg transition disabled:opacity-40"
        >
          {started ? "Send" : "Ask"}
        </button>
      </div>
    </form>
  );

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-2xl flex-col px-4 sm:px-6">
      <header className="flex items-center justify-between py-6 text-sm text-muted">
        <button type="button" onClick={reset} className="font-medium text-ink">
          US Customs Assistant
        </button>
        {started ? (
          <button type="button" onClick={reset} disabled={busy} className="hover:text-ink disabled:opacity-40">
            New question
          </button>
        ) : (
          <span>Alcohol &amp; tobacco · v1</span>
        )}
      </header>

      {!started ? (
        <section className="flex flex-1 flex-col justify-center gap-10 pb-24">
          <div className="space-y-4">
            <h1 className="font-serif text-4xl leading-tight tracking-tight sm:text-5xl">
              What are you bringing home?
            </h1>
            <p className="max-w-xl text-lg leading-relaxed text-muted">
              Tell us what you bought abroad. You get your allowance, an estimate of any duty and
              tax, anything that can&rsquo;t come in, and the rule behind each point.
            </p>
          </div>
          {composer}
          <div className="flex flex-col gap-2">
            <span className="text-xs uppercase tracking-[0.14em] text-muted">Try</span>
            <div className="flex flex-wrap gap-2">
              {EXAMPLES.map((q) => (
                <button
                  key={q}
                  type="button"
                  onClick={() => setQuestion(q)}
                  className="rounded-full border border-line px-3.5 py-1.5 text-left text-sm text-muted transition hover:border-accent hover:text-ink"
                >
                  {q.length > 58 ? `${q.slice(0, 56)}…` : q}
                </button>
              ))}
            </div>
          </div>
        </section>
      ) : (
        <section className="flex flex-1 flex-col gap-5 pb-6">
          {turns.map((t) =>
            t.role === "user" ? (
              <p
                key={t.id}
                className="ml-auto max-w-[85%] rounded-2xl bg-surface-2 px-4 py-2.5 text-[15px] leading-relaxed"
              >
                {t.text}
              </p>
            ) : t.card.outcome === "clarify" ? (
              <ClarifyCard
                key={t.id}
                card={t.card}
                busy={busy}
                answered={t.id !== lastAssistant}
                onReply={ask}
              />
            ) : (
              <AnswerCard
                key={t.id}
                card={t.card}
                facts={t.id === lastAssistant ? facts : null}
                latest={t.id === lastAssistant}
                busy={busy}
                onEdit={edit}
              />
            ),
          )}
          {progress && <Progress state={progress} />}
          {error && (
            <p className="rounded-xl border border-bad/40 bg-bad-soft px-3.5 py-2.5 text-sm" role="alert">
              {error}
            </p>
          )}
          <div ref={bottom} />
          <div className="sticky bottom-0 mt-auto bg-gradient-to-t from-bg from-70% to-transparent pt-8 pb-4">
            {composer}
          </div>
        </section>
      )}

      <footer className="border-t border-line py-5 text-xs leading-relaxed text-muted">
        <p>
          Estimates only. The CBP officer&rsquo;s assessment is final. This assistant never fills in
          or submits a declaration for you.
        </p>
        <p className="mt-1">API: {apiNote}</p>
      </footer>
    </main>
  );
}
