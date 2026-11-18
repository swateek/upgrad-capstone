import type { Card } from "@/lib/api";

// One small mark per answer: what kind of answer this is, in plain words.
const MARKS: Record<string, { text: string; tone: string }> = {
  owe: { text: "You'll owe", tone: "bg-accent-soft text-accent" },
  nothing_owed: { text: "Nothing to pay", tone: "bg-ok-soft text-ok" },
  prohibited: { text: "Can't come in", tone: "bg-bad-soft text-bad" },
  seizure_risk: { text: "Over the limit", tone: "bg-warn-soft text-warn" },
  mixed: { text: "Mixed", tone: "bg-warn-soft text-warn" },
  clarify: { text: "One question", tone: "bg-surface-2 text-muted" },
  refused: { text: "Can't help with that", tone: "bg-surface-2 text-muted" },
  out_of_scope: { text: "Not covered", tone: "bg-surface-2 text-muted" },
  escalated: { text: "Ask CBP", tone: "bg-warn-soft text-warn" },
};

export function Status({ card }: { card: Card }) {
  const mark = MARKS[card.kind] ?? MARKS[card.outcome] ?? MARKS.clarify;
  return (
    <div className="flex items-center gap-2">
      <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${mark.tone}`}>
        {mark.text}
      </span>
      {card.outcome === "answered" && (
        <span className="text-xs text-muted">Figures and sources checked</span>
      )}
      {card.meta?.cached && (
        <span className="rounded-full border border-line px-2 py-0.5 text-xs text-muted">
          Cached answer
        </span>
      )}
    </div>
  );
}
