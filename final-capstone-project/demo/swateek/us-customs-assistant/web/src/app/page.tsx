"use client";

import { useEffect, useState } from "react";

// Scaffold of the Ask screen (plan §9). The composer is wired to /api/chat once the agent
// graph exists; until then it shows the API's health so the stack can be checked end to end.

const EXAMPLES = [
  "Back from 10 days in Italy with four bottles of wine, 750 ml each, $30 a bottle. Do I owe anything?",
  "Coming home from Cancún. I bought a box of 25 Cuban cigars and a bottle of Cuban rum there. Is that fine?",
  "Flying home from Dubai after two weeks. I bought two cartons of cigarettes (400) at duty-free.",
  "Day trip to Tijuana. I bought one 750 ml bottle of tequila.",
];

type Health = { status: string; version: string; mode: string; endpoints: string } | null;

export default function Home() {
  const [question, setQuestion] = useState("");
  const [health, setHealth] = useState<Health>(null);
  const [apiDown, setApiDown] = useState(false);

  useEffect(() => {
    fetch("/api/health", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setHealth)
      .catch(() => setApiDown(true));
  }, []);

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-2xl flex-col px-4 sm:px-6">
      <header className="flex items-center justify-between py-6 text-sm text-muted">
        <span className="font-medium text-ink">US Customs Assistant</span>
        <span>Alcohol &amp; tobacco · v1</span>
      </header>

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

        <form
          className="rounded-2xl border border-line bg-surface p-3 shadow-[0_1px_2px_rgba(0,0,0,0.04)] transition focus-within:border-accent"
          onSubmit={(e) => e.preventDefault()}
        >
          <label htmlFor="question" className="sr-only">
            Your question
          </label>
          <textarea
            id="question"
            rows={3}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="e.g. Two bottles of whisky from Scotland after a week away"
            className="w-full resize-none bg-transparent px-2 py-1.5 text-base leading-relaxed outline-none placeholder:text-muted/70"
          />
          <div className="flex items-center justify-between gap-3 px-2 pt-1">
            <span className="text-xs text-muted">The assistant is not connected yet.</span>
            <button
              type="submit"
              disabled
              className="rounded-full bg-ink px-4 py-1.5 text-sm font-medium text-bg opacity-40"
            >
              Ask
            </button>
          </div>
        </form>

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

      <footer className="border-t border-line py-5 text-xs leading-relaxed text-muted">
        <p>
          Estimates only. The CBP officer&rsquo;s assessment is final. Always declare what you
          bring.
        </p>
        <p className="mt-1">
          API:{" "}
          {apiDown
            ? "not reachable"
            : health
              ? `${health.status} · ${health.mode} · endpoints ${health.endpoints}`
              : "checking…"}
        </p>
      </footer>
    </main>
  );
}
