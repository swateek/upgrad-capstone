"use client";

import { useState } from "react";
import type { Card } from "@/lib/api";
import { Status } from "./Status";

// One short question (SPEC §6), with quick replies for the yes/no facts and a text field for
// the rest (state, where it was made, price). The reply goes back as a normal message.

const QUICK: Record<string, string[]> = {
  age_21_plus: ["I'm 21 or older", "I'm under 21"],
  trip_hours_or_arrived_from_mexico: [
    "I was away more than 48 hours",
    "I was away less than 48 hours",
    "I came straight back from Mexico",
  ],
  exemption_used_last_30_days: [
    "I haven't used my exemption in the last 30 days",
    "I used my exemption in the last 30 days",
  ],
};

export function ClarifyCard({
  card,
  busy,
  answered,
  onReply,
}: {
  card: Card;
  busy: boolean;
  answered: boolean;
  onReply: (text: string) => void;
}) {
  const groups = card.clarify_fields.filter((f) => QUICK[f]);
  const [picked, setPicked] = useState<Record<string, string>>({});
  const [text, setText] = useState("");
  const reply = [...groups.map((g) => picked[g]).filter(Boolean), text.trim()].filter(Boolean).join(". ");

  return (
    <article className="space-y-4 rounded-2xl border border-line bg-surface p-5">
      <Status card={card} />
      <p className="font-serif text-xl leading-snug">{card.bottom_line}</p>
      {!answered && (
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (reply) onReply(reply.endsWith(".") ? reply : `${reply}.`);
          }}
        >
          {groups.map((g) => (
            <div key={g} className="flex flex-wrap gap-2">
              {QUICK[g].map((opt) => (
                <button
                  key={opt}
                  type="button"
                  aria-pressed={picked[g] === opt}
                  onClick={() => setPicked({ ...picked, [g]: picked[g] === opt ? "" : opt })}
                  className={`rounded-full border px-3 py-1.5 text-sm transition ${
                    picked[g] === opt
                      ? "border-accent bg-accent-soft text-ink"
                      : "border-line text-muted hover:border-accent hover:text-ink"
                  }`}
                >
                  {opt}
                </button>
              ))}
            </div>
          ))}
          <div className="flex gap-2">
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={groups.length ? "Anything else (e.g. landing in California)" : "Your answer"}
              className="flex-1 rounded-full border border-line bg-bg px-4 py-1.5 text-sm outline-none focus:border-accent"
            />
            <button
              type="submit"
              disabled={!reply || busy}
              className="rounded-full bg-ink px-4 py-1.5 text-sm font-medium text-bg transition disabled:opacity-40"
            >
              Reply
            </button>
          </div>
        </form>
      )}
    </article>
  );
}
