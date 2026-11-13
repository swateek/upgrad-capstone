"use client";

import { useEffect, useState } from "react";
import { api, isError, type Bidder, type CaseListing, type ScoreRow, type ScoreSheet } from "@/lib/api";
import { Badge, Button, Callout, ErrorNote, Panel, Spinner, inputCls, inr } from "./ui";

const statusTone = { responsive: "ok", non_responsive: "warn", withheld_screening: "bad" } as const;
const statusLabel = {
  responsive: "responsive",
  non_responsive: "non-responsive",
  withheld_screening: "withheld (screening)",
} as const;

function ScoreCell({ row }: { row: ScoreRow }) {
  if (row.gap) return <span className="text-warn">gap: {row.gap}</span>;
  if (row.score === "pass") return <Badge tone="ok">pass</Badge>;
  if (row.score === "fail") return <Badge tone="bad">fail</Badge>;
  return (
    <span className="whitespace-nowrap font-mono">
      {row.score} / {row.weight}
    </span>
  );
}

function BidderSummary({ bidders, ranking }: { bidders: Bidder[]; ranking: string[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="text-xs text-muted">
          <tr>
            <th className="py-2 pr-3">Bidder</th>
            <th className="py-2 pr-3">Status</th>
            <th className="py-2 pr-3">Technical total</th>
            <th className="py-2 pr-3">Quoted price</th>
            <th className="py-2 pr-3">Draft rank</th>
            <th className="py-2">Screening</th>
          </tr>
        </thead>
        <tbody>
          {bidders.map((b) => {
            const rank = ranking.indexOf(b.bidder);
            return (
              <tr key={b.bidder} className="border-t border-line align-top">
                <td className="py-2 pr-3">
                  <div className="font-medium">{b.bidder}</div>
                  <div className="text-xs text-muted">{b.name}</div>
                </td>
                <td className="py-2 pr-3">
                  <Badge tone={statusTone[b.status]}>{statusLabel[b.status]}</Badge>
                  {b.failed_mandatory.length > 0 && (
                    <div className="mt-1 text-xs text-muted">failed {b.failed_mandatory.join(", ")}</div>
                  )}
                </td>
                <td className="py-2 pr-3 font-mono">{b.technical_total ?? "—"}</td>
                <td className="py-2 pr-3">
                  {b.price_gap ? <span className="text-warn">gap: {b.price_gap}</span> : inr(b.quoted_price_inr)}
                </td>
                <td className="py-2 pr-3 font-mono">{rank >= 0 ? rank + 1 : "—"}</td>
                <td className="py-2 text-xs">
                  {b.screening.hits.length > 0 ? (
                    <span className="text-bad">
                      present on {b.screening.hits.map((h) => `${h.list}${h.synthetic ? " (synthetic)" : ""} as of ${h.snapshot_date}`).join("; ")}
                    </span>
                  ) : (
                    <span className="text-muted">not present</span>
                  )}
                  {b.screening.history_versions.length > 0 && (
                    <div className="text-muted">older list versions: {b.screening.history_versions.join(", ")}</div>
                  )}
                  {b.screening.possible_matches.length > 0 && (
                    <div className="text-warn">possible match (verify): {b.screening.possible_matches.join(", ")}</div>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

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

  const byBidder = (rows: ScoreRow[]) =>
    rows.reduce<Record<string, ScoreRow[]>>((acc, r) => ((acc[r.bidder] ??= []).push(r), acc), {});

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

      {sheet && (
        <>
          <Callout tone="accent">
            <strong>{sheet.draft_notice}</strong> {sheet.title}
          </Callout>
          {sheet.withheld_bidders.length > 0 && (
            <Callout tone="bad">
              Withheld from the draft ranking because the name is present on a screening list:{" "}
              {sheet.withheld_bidders.map((w) => `${w.bidder} (${w.name})`).join(", ")}. A listed firm cannot be
              recommended.
            </Callout>
          )}
          <Panel>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">Bidders</h2>
            <BidderSummary bidders={sheet.bidders} ranking={sheet.ranking_eligible} />
          </Panel>
          {Object.entries(byBidder(sheet.rows)).map(([bidder, rows]) => (
            <Panel key={bidder}>
              <h3 className="mb-2 text-sm font-semibold">
                {bidder} · {sheet.bidders.find((b) => b.bidder === bidder)?.name}
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="text-xs text-muted">
                    <tr>
                      <th className="py-1 pr-3">Req.</th>
                      <th className="py-1 pr-3">Requirement</th>
                      <th className="py-1 pr-3">Quoted evidence</th>
                      <th className="py-1">Score</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.requirement_id} className="border-t border-line align-top">
                        <td className="py-1.5 pr-3 font-mono text-xs">
                          {r.requirement_id}
                          <div className="text-muted">{r.kind}</div>
                        </td>
                        <td className="py-1.5 pr-3">{r.requirement}</td>
                        <td className="py-1.5 pr-3 text-xs text-muted">{r.quoted_evidence ?? "—"}</td>
                        <td className="py-1.5 text-xs">
                          <ScoreCell row={r} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
          ))}
        </>
      )}
    </div>
  );
}
