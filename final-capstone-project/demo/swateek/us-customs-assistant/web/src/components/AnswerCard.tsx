"use client";

import { useState } from "react";
import type { Card, Facts } from "@/lib/api";
import { FactsEditor, type FactEdits } from "./FactsEditor";
import { Status } from "./Status";

// The answer card (SPEC §4): bottom line first, then the working, the figures, notes, the facts
// relied on (editable: a change replans), sources with the as-of date, and the officer note.

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <h3 className="text-xs font-medium uppercase tracking-[0.14em] text-muted">{title}</h3>
      {children}
    </section>
  );
}

const NOTE_TONE: Record<string, string> = {
  seizure_risk: "border-warn/40 bg-warn-soft",
  us_export_labelled_relinquish: "border-warn/40 bg-warn-soft",
  cuban_prohibited: "border-bad/40 bg-bad-soft",
  possibly_cuban_declare: "border-bad/40 bg-bad-soft",
  large_quantity: "border-warn/40 bg-warn-soft",
};

export function AnswerCard({
  card,
  facts,
  latest,
  busy,
  onEdit,
}: {
  card: Card;
  facts: Facts | null;
  latest: boolean;
  busy: boolean;
  onEdit: (edits: FactEdits) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [showFigures, setShowFigures] = useState(false);
  const canEdit = latest && !!facts && facts.basket.length > 0 && card.facts_relied_on.length > 0;

  return (
    <article className="space-y-6 rounded-2xl border border-line bg-surface p-5 sm:p-6">
      <div className="space-y-3">
        <Status card={card} />
        <p className="font-serif text-2xl leading-snug tracking-tight">{card.bottom_line}</p>
      </div>

      {card.working.length > 0 && (
        <Section title="How we got there">
          <ul className="space-y-1.5 text-[15px] leading-relaxed">
            {card.working.map((w) => (
              <li key={w} className="flex gap-2.5">
                <span className="mt-2.5 size-1 shrink-0 rounded-full bg-muted" aria-hidden />
                <span>{w}</span>
              </li>
            ))}
          </ul>
          {card.figures.length > 0 && (
            <div>
              <button
                type="button"
                onClick={() => setShowFigures(!showFigures)}
                className="text-xs text-muted underline-offset-4 hover:text-ink hover:underline"
                aria-expanded={showFigures}
              >
                {showFigures ? "Hide the figures" : "Show every figure"}
              </button>
              {showFigures && (
                <table className="mt-2 w-full text-sm">
                  <tbody>
                    {card.figures.map((f) => (
                      <tr key={f.handle} className="border-t border-line">
                        <td className="py-1.5 pr-4 text-muted">{f.label}</td>
                        <td className="py-1.5 text-right tabular-nums">{f.display}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}
        </Section>
      )}

      {card.notes.length > 0 && (
        <div className="space-y-2">
          {card.notes.map((n) => (
            <p
              key={n.id}
              className={`rounded-xl border px-3.5 py-2.5 text-sm leading-relaxed ${
                NOTE_TONE[n.id] ?? "border-line bg-surface-2"
              }`}
            >
              {n.text}
            </p>
          ))}
        </div>
      )}

      {card.facts_relied_on.length > 0 && (
        <Section title="Facts we relied on">
          {editing && facts ? (
            <FactsEditor
              facts={facts}
              busy={busy}
              onCancel={() => setEditing(false)}
              onSubmit={(e) => {
                setEditing(false);
                onEdit(e);
              }}
            />
          ) : (
            <>
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
                {card.facts_relied_on.map((f, i) => (
                  <div key={`${f.label}-${i}`} className="contents">
                    <dt className="text-muted">{f.label}</dt>
                    <dd>{f.value}</dd>
                  </div>
                ))}
              </dl>
              {canEdit && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => setEditing(true)}
                  className="text-sm text-accent underline-offset-4 hover:underline disabled:opacity-40"
                >
                  Something wrong? Edit the facts
                </button>
              )}
            </>
          )}
        </Section>
      )}

      {card.sources.length > 0 && (
        <Section title="Sources">
          <ul className="space-y-1 text-sm">
            {card.sources.map((s) => (
              <li key={s.clause_id}>
                {s.url ? (
                  <a
                    href={s.url}
                    target="_blank"
                    rel="noreferrer"
                    className="underline decoration-line underline-offset-4 hover:decoration-accent"
                  >
                    {s.citation}
                  </a>
                ) : (
                  s.citation
                )}
              </li>
            ))}
          </ul>
        </Section>
      )}

      <footer className="space-y-1 border-t border-line pt-4 text-xs leading-relaxed text-muted">
        <p>{card.disclaimer}</p>
        <p>{card.as_of}</p>
      </footer>
    </article>
  );
}
