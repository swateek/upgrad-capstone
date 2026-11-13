"use client";

import { useEffect, useState } from "react";
import { api, isError, type CaseListing, type ScoreSheet } from "@/lib/api";
import { ScoreSheetView } from "./results";
import { Button, ErrorNote, Panel, Spinner, inputCls } from "./ui";

export function BidMode() {
  const [cases, setCases] = useState<CaseListing[]>([]);
  const [caseId, setCaseId] = useState("case_001");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sheet, setSheet] = useState<ScoreSheet | null>(null);

  useEffect(() => {
    api.cases().then(setCases).catch((e: Error) => setError(e.message));
  }, []);

  async function score(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSheet(null);
    try {
      const r = await api.tool<ScoreSheet>("score_bids", { case_id: caseId });
      if (isError(r.result)) setError(r.result.error);
      else setSheet(r.result);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <Panel>
        <form onSubmit={score} className="flex flex-wrap items-end gap-3">
          <div className="min-w-72 flex-1">
            <label className="mb-1 block text-sm font-medium" htmlFor="case">
              Preloaded bid case (synthetic)
            </label>
            <select id="case" className={inputCls} value={caseId} onChange={(e) => setCaseId(e.target.value)}>
              {cases.map((c) => (
                <option key={c.case_id} value={c.case_id}>
                  {c.case_id} · {c.title}
                  {c.has_requirement_sheet ? "" : " (no evaluation sheet)"}
                </option>
              ))}
            </select>
          </div>
          <Button type="submit" disabled={busy || cases.length === 0}>
            Draft score sheet
          </Button>
          {busy && <Spinner label="Scoring against the stored sheet…" />}
        </form>
        <p className="mt-3 text-xs text-muted">
          Scores come from the evaluation sheet stored with each case, computed in code. Missing evidence is a
          gap, never a guessed number. There is no award, order or debarment control here.
        </p>
      </Panel>
      {error && <ErrorNote message={error} />}
      {sheet && <ScoreSheetView sheet={sheet} />}
    </div>
  );
}
