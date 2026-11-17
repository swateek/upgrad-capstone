"use client";

import { useState } from "react";
import { api, type AnswerResult } from "@/lib/api";
import { Badge, Button, Callout, ErrorNote, Panel, Spinner, inputCls } from "./ui";

const CITE = /\[([a-z0-9_]+:[^\]\s]+)\]/g;

function AnswerText({ text, onCite }: { text: string; onCite: (c: string) => void }) {
  const parts: React.ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(CITE)) {
    parts.push(text.slice(last, m.index));
    const c = m[1];
    parts.push(
      <button
        key={`${c}-${m.index}`}
        onClick={() => onCite(c)}
        className="mx-0.5 rounded bg-accent-soft px-1.5 py-0.5 font-mono text-[11px] text-accent hover:underline"
        title="Show source"
      >
        {c}
      </button>,
    );
    last = (m.index ?? 0) + m[0].length;
  }
  parts.push(text.slice(last));
  return <p className="leading-7">{parts}</p>;
}

export function PolicyMode({ instruments }: { instruments: string[] }) {
  const [question, setQuestion] = useState("");
  const [instrument, setInstrument] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AnswerResult | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  async function ask(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await api.answer(question.trim(), instrument));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function showSource(c: string) {
    setOpen(c);
    document.getElementById(`src-${c}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  return (
    <div className="space-y-4">
      <Panel>
        <form onSubmit={ask} className="space-y-3">
          <label className="block text-sm font-medium" htmlFor="q">
            Ask about a rule, threshold, exception or approval
          </label>
          <textarea
            id="q"
            rows={3}
            className={inputCls}
            placeholder="e.g. Up to what value can goods not on GeM be bought without quotations?"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
          />
          <div className="flex flex-wrap items-center gap-3">
            <select
              aria-label="Restrict to one instrument"
              className={`${inputCls} w-auto`}
              value={instrument}
              onChange={(e) => setInstrument(e.target.value)}
            >
              <option value="">All instruments</option>
              {instruments.map((i) => (
                <option key={i} value={i}>
                  {i}
                </option>
              ))}
            </select>
            <Button type="submit" disabled={busy || question.trim().length < 3}>
              Ask
            </Button>
            {busy && <Spinner label="Retrieving rules and drafting an answer…" />}
          </div>
        </form>
      </Panel>

      {error && <ErrorNote message={error} />}

      {result && (
        <>
          <Panel>
            <div className="mb-3 flex items-center justify-between gap-2">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">Draft answer</h2>
              <span className="text-xs text-muted">{result.latency_s}s</span>
            </div>
            <AnswerText text={result.answer} onCite={showSource} />
            {result.uncited_sentences.length > 0 && (
              <div className="mt-4">
                <Callout tone="warn">
                  {result.uncited_sentences.length} sentence(s) carry no citation. Treat them as unverified.
                </Callout>
              </div>
            )}
            {result.citations.length === 0 && (
              <div className="mt-4">
                <Callout tone="bad">No citation from the retrieved rules. Do not rely on this answer.</Callout>
              </div>
            )}
          </Panel>

          <Panel>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">
              Retrieved rule text ({result.hits.length})
            </h2>
            <ul className="space-y-2">
              {result.hits.map((h, i) => {
                const cited = result.citations.includes(h.citation);
                const isOpen = open === h.citation;
                return (
                  <li key={`${h.citation}-${i}`} id={`src-${h.citation}`} className="rounded-lg border border-line">
                    <button
                      onClick={() => setOpen(isOpen ? null : h.citation)}
                      className="flex w-full flex-wrap items-center gap-2 px-3 py-2 text-left"
                    >
                      <span className="font-mono text-xs text-accent">{h.citation}</span>
                      {h.part > 1 && <Badge>part {h.part}</Badge>}
                      <span className="text-sm">{h.title}</span>
                      {h.synthetic && <Badge tone="warn">synthetic</Badge>}
                      {cited && <Badge tone="ok">cited</Badge>}
                      <span className="ml-auto text-xs text-muted">edition {h.edition_date ?? "n/a"}</span>
                    </button>
                    {isOpen && (
                      <pre className="max-h-80 overflow-auto whitespace-pre-wrap border-t border-line px-3 py-2 text-xs leading-5 text-muted">
                        {h.text}
                      </pre>
                    )}
                  </li>
                );
              })}
            </ul>
          </Panel>
        </>
      )}
    </div>
  );
}
