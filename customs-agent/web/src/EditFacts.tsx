import { useState } from "react";
import type { Facts } from "./types";

export interface Change {
  field: string;
  value: unknown;
  label: string;
}

/** Correct a fact on the card. Each change is one turn: the agent re-runs only the steps that
 * depend on it. */
export function EditFacts({ facts, onSave, onCancel }: { facts: Facts; onSave: (c: Change[]) => void; onCancel: () => void }) {
  const p = facts.profile;
  const [age, setAge] = useState(p.age != null ? String(p.age) : "");
  const [tripValue, setTripValue] = useState(p.trip ? String(p.trip.value) : "");
  const [tripUnit, setTripUnit] = useState(p.trip?.unit ?? "days");
  const [used, setUsed] = useState(p.exemption_used_last_30_days == null ? "" : p.exemption_used_last_30_days ? "yes" : "no");
  const [counts, setCounts] = useState(facts.basket.map((b) => String(b.quantity.value)));

  const save = (e: React.FormEvent) => {
    e.preventDefault();
    const out: Change[] = [];
    if (age && Number(age) !== p.age) out.push({ field: "age", value: Number(age), label: `age to ${age}` });
    if (tripValue && (Number(tripValue) !== p.trip?.value || tripUnit !== p.trip?.unit)) {
      out.push({ field: "trip", value: { value: Number(tripValue), unit: tripUnit }, label: `time abroad to ${tripValue} ${tripUnit}` });
    }
    if (used && (used === "yes") !== p.exemption_used_last_30_days) {
      out.push({ field: "exemption_used_last_30_days", value: used === "yes", label: `exemption used in the last 30 days to ${used}` });
    }
    facts.basket.forEach((b, i) => {
      if (counts[i] && Number(counts[i]) !== b.quantity.value) {
        out.push({
          field: `item${i + 1}.quantity`,
          value: { ...b.quantity, value: Number(counts[i]) },
          label: `${b.item} to ${counts[i]} ${b.quantity.unit}`,
        });
      }
    });
    onSave(out);
  };

  return (
    <form className="edit" onSubmit={save}>
      <label>
        Age
        <input type="number" min={0} max={120} value={age} onChange={(e) => setAge(e.target.value)} />
      </label>
      <label>
        Time abroad
        <span className="edit__pair">
          <input type="number" min={0} step="any" value={tripValue} onChange={(e) => setTripValue(e.target.value)} />
          <select value={tripUnit} onChange={(e) => setTripUnit(e.target.value)}>
            <option value="hours">hours</option>
            <option value="days">days</option>
            <option value="weeks">weeks</option>
          </select>
        </span>
      </label>
      <label>
        Used your exemption in the last 30 days
        <select value={used} onChange={(e) => setUsed(e.target.value)}>
          <option value="">not said</option>
          <option value="no">no</option>
          <option value="yes">yes</option>
        </select>
      </label>
      {facts.basket.map((b, i) => (
        <label key={i}>
          {b.item} ({b.quantity.unit})
          <input
            type="number"
            min={0}
            step="any"
            value={counts[i]}
            onChange={(e) => setCounts(counts.map((c, j) => (j === i ? e.target.value : c)))}
          />
        </label>
      ))}
      <div className="edit__actions">
        <button type="submit">Recalculate</button>
        <button type="button" className="edit__cancel" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
