import type { AskResponse, LineType } from "./types";

export const money = (n: number) =>
  n.toLocaleString("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2 });

export const LINE_TEXT: Record<LineType, string> = {
  owe: "Over your allowance",
  nothing_to_pay: "Within your allowance",
  prohibited: "Prohibited",
  declare_detention_risk: "Over the tobacco allowance: may be detained",
  relinquish_excess: "Over the allowance: hand the excess to CBP",
};

export type Tone = "owe" | "clear" | "hold" | "stop";

/** The band at the top of the slip: what a traveller needs to know first, built from the
 * structured answer (code), never from the model's wording. */
export function headline(r: AskResponse): { tone: Tone; title: string; sub?: string } {
  const a = r.answer;
  const items = r.card.items ?? [];
  if (r.outcome === "clarify") return { tone: "hold", title: "One more detail" };
  if (r.outcome === "escalated") return { tone: "hold", title: "Ask a CBP officer", sub: "This one needs an officer's decision." };
  if (r.outcome === "refused" || !a) return { tone: "stop", title: "Not something I can assess" };
  if (a.whatif) {
    return {
      tone: "clear",
      title: `Up to ${a.whatif.max_units} bottles`,
      sub: `You would owe ${money(a.whatif.owed_usd)}`,
    };
  }
  const banned = items.filter((i) => i.type === "prohibited");
  if (banned.length && banned.length === items.length) {
    return { tone: "owe", title: `You can't bring ${banned.length === 1 ? banned[0].item : "these items"} in` };
  }
  if ((a.total_usd ?? 0) > 0) {
    const sub = banned.length ? `${banned.map((b) => b.item).join(", ")}: prohibited` : undefined;
    return { tone: "owe", title: `You owe ${money(a.total_usd!)}`, sub };
  }
  if (items.some((i) => i.type === "declare_detention_risk" || i.type === "relinquish_excess")) {
    return { tone: "owe", title: "Declare it: over the allowance" };
  }
  if (banned.length) return { tone: "owe", title: `${banned.map((b) => b.item).join(", ")}: prohibited` };
  return { tone: "clear", title: "Nothing to pay", sub: "Still declare everything you bring." };
}

/** "Age: 34" -> ["Age", "34"] */
export function splitFact(f: string): [string, string] {
  const i = f.indexOf(": ");
  return i < 0 ? [f, ""] : [f.slice(0, i), f.slice(i + 2)];
}
