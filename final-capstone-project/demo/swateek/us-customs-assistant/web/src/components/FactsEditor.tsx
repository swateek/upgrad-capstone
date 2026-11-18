"use client";

import { useState } from "react";
import type { Facts } from "@/lib/api";

// Edit the facts the answer relied on. Only changed fields are sent; the backend phrases them as
// a correction ("Correction to my facts: I am 20 years old."), and the agent replans.

export type FactEdits = {
  profile: Record<string, unknown>;
  lines: Record<string, Record<string, unknown>>;
};

type Field = { key: string; label: string; kind: "number" | "text" | "yesno"; hint?: string };

const PROFILE: Field[] = [
  { key: "age", label: "Age", kind: "number" },
  { key: "trip_hours", label: "Time away (hours)", kind: "number", hint: "a week = 168" },
  { key: "arrived_directly_from", label: "Arrived directly from", kind: "text", hint: "country code, e.g. FR" },
  { key: "exemption_used_last_30_days", label: "Exemption used in the last 30 days", kind: "yesno" },
  { key: "arrival_state", label: "Arrival state", kind: "text", hint: "e.g. CA" },
];
const LINE: Field[] = [
  { key: "quantity", label: "Quantity", kind: "number" },
  { key: "container_ml", label: "Size (ml each)", kind: "number" },
  { key: "abv", label: "Alcohol %", kind: "number" },
  { key: "value_usd", label: "Paid in total ($)", kind: "number" },
  { key: "origin", label: "Made in", kind: "text", hint: "country code" },
];

const show = (v: unknown) => (v === undefined || v === null ? "" : String(v));

function parse(f: Field, raw: string): unknown {
  if (f.kind === "number") return raw.trim() === "" ? undefined : Number(raw);
  if (f.kind === "yesno") return raw === "yes" ? true : raw === "no" ? false : undefined;
  return raw.trim() === "" ? undefined : raw.trim().toUpperCase();
}

function Input({ f, value, onChange }: { f: Field; value: string; onChange: (v: string) => void }) {
  const cls =
    "w-full rounded-lg border border-line bg-bg px-2.5 py-1.5 text-sm outline-none focus:border-accent";
  if (f.kind === "yesno")
    return (
      <select className={cls} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">not given</option>
        <option value="no">no</option>
        <option value="yes">yes</option>
      </select>
    );
  return (
    <input
      className={cls}
      inputMode={f.kind === "number" ? "decimal" : "text"}
      value={value}
      placeholder={f.hint}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

export function FactsEditor({
  facts,
  busy,
  onSubmit,
  onCancel,
}: {
  facts: Facts;
  busy: boolean;
  onSubmit: (edits: FactEdits) => void;
  onCancel: () => void;
}) {
  const initialProfile = Object.fromEntries(
    PROFILE.map((f) => {
      const v = facts.profile[f.key];
      return [f.key, f.kind === "yesno" ? (v === true ? "yes" : v === false ? "no" : "") : show(v)];
    }),
  );
  const initialLines = facts.basket.map((ln) => Object.fromEntries(LINE.map((f) => [f.key, show(ln[f.key])])));
  const [profile, setProfile] = useState<Record<string, string>>(initialProfile);
  const [lines, setLines] = useState<Record<string, string>[]>(initialLines);

  const edits = (): FactEdits => {
    const p: Record<string, unknown> = {};
    for (const f of PROFILE) {
      if (profile[f.key] !== initialProfile[f.key]) {
        const v = parse(f, profile[f.key]);
        if (v !== undefined) p[f.key] = v;
      }
    }
    const l: Record<string, Record<string, unknown>> = {};
    lines.forEach((ln, i) => {
      const e: Record<string, unknown> = {};
      for (const f of LINE) {
        if (ln[f.key] !== initialLines[i][f.key]) {
          const v = parse(f, ln[f.key]);
          if (v !== undefined) e[f.key] = v;
        }
      }
      if (Object.keys(e).length) l[String(i + 1)] = e;
    });
    return { profile: p, lines: l };
  };
  const e = edits();
  const changed = Object.keys(e.profile).length + Object.keys(e.lines).length > 0;

  return (
    <form
      className="space-y-5"
      onSubmit={(ev) => {
        ev.preventDefault();
        if (changed) onSubmit(e);
      }}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        {PROFILE.map((f) => (
          <label key={f.key} className="space-y-1 text-xs text-muted">
            <span>{f.label}</span>
            <Input f={f} value={profile[f.key]} onChange={(v) => setProfile({ ...profile, [f.key]: v })} />
          </label>
        ))}
      </div>
      {facts.basket.map((ln, i) => (
        <fieldset key={i} className="space-y-2 rounded-xl border border-line p-3">
          <legend className="px-1 text-xs font-medium text-ink">
            Item {i + 1}: {String(ln.item ?? "item").replace("_", " ")}
          </legend>
          <div className="grid gap-3 sm:grid-cols-3">
            {LINE.map((f) => (
              <label key={f.key} className="space-y-1 text-xs text-muted">
                <span>{f.label}</span>
                <Input
                  f={f}
                  value={lines[i][f.key]}
                  onChange={(v) => setLines(lines.map((x, j) => (j === i ? { ...x, [f.key]: v } : x)))}
                />
              </label>
            ))}
          </div>
        </fieldset>
      ))}
      <div className="flex items-center gap-2">
        <button
          type="submit"
          disabled={!changed || busy}
          className="rounded-full bg-ink px-4 py-1.5 text-sm font-medium text-bg transition disabled:opacity-40"
        >
          Recalculate
        </button>
        <button type="button" onClick={onCancel} className="rounded-full px-3 py-1.5 text-sm text-muted hover:text-ink">
          Cancel
        </button>
      </div>
    </form>
  );
}
