"use client";

import type { Bidder, ScoreRow, ScoreSheet, ScreeningResult } from "@/lib/api";
import { Badge, Callout, Panel, inr } from "./ui";

// Shared result views: used by the direct tool modes and by the assistant chat.

export function ScreeningCard({ result }: { result: ScreeningResult }) {
  return (
    <Panel>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Badge tone={result.status === "present" ? "bad" : "neutral"}>
          {result.status === "present" ? "Present on a list" : "Not present in the snapshot"}
        </Badge>
        <span className="text-xs text-muted">matched as: {result.normalized_query}</span>
      </div>
      <p className="mb-4 font-medium">{result.statement}</p>
      <div className="space-y-3">
        {result.lists.map((l) => (
          <div key={l.list} className="rounded-lg border border-line p-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-semibold">{l.title}</span>
              {l.synthetic && <Badge tone="warn">synthetic sample</Badge>}
              <Badge tone={l.status === "present" ? "bad" : "neutral"}>{l.status.replace("_", " ")}</Badge>
              <span className="ml-auto text-xs text-muted">snapshot {l.snapshot_date}</span>
            </div>
            {l.matches.length > 0 && (
              <div className="mt-2 overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="text-muted">
                    <tr>
                      <th className="py-1 pr-3">Supplier</th>
                      <th className="py-1 pr-3">Brand</th>
                      <th className="py-1 pr-3">Category</th>
                      <th className="py-1">Period / entity</th>
                    </tr>
                  </thead>
                  <tbody>
                    {l.matches.slice(0, 10).map((m, i) => (
                      <tr key={i} className="border-t border-line">
                        <td className="py-1 pr-3">{m.supplier_name}</td>
                        <td className="py-1 pr-3">{m.brand || "—"}</td>
                        <td className="py-1 pr-3">{m.category}</td>
                        <td className="py-1">{[m.period, m.debarring_entity].filter(Boolean).join(" · ") || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {l.matched_rows > 10 && (
                  <p className="mt-1 text-xs text-muted">{l.matched_rows - 10} more matching rows not shown.</p>
                )}
              </div>
            )}
            {l.history_versions.length > 0 && (
              <div className="mt-2">
                <Callout tone="accent">
                  Appeared in older version(s) of this list ({l.history_versions.join(", ")}) but not in the
                  latest version dated {l.snapshot_date}. No reason for the change is recorded here.
                </Callout>
              </div>
            )}
            {l.possible_matches.length > 0 && (
              <div className="mt-2">
                <Callout tone="warn">
                  Possible match, needs human verification:{" "}
                  {l.possible_matches.map((p) => `${p.listed_name} (${p.reason})`).join("; ")}. This is not a
                  finding.
                </Callout>
              </div>
            )}
            {(l.scope || l.disclaimer) && (
              <p className="mt-2 text-xs text-muted">
                {l.scope} {l.disclaimer}
              </p>
            )}
          </div>
        ))}
      </div>
    </Panel>
  );
}

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
                      present on{" "}
                      {b.screening.hits
                        .map((h) => `${h.list}${h.synthetic ? " (synthetic)" : ""} as of ${h.snapshot_date}`)
                        .join("; ")}
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

export function ScoreSheetView({ sheet, detailed = true }: { sheet: ScoreSheet; detailed?: boolean }) {
  const byBidder = sheet.rows.reduce<Record<string, ScoreRow[]>>(
    (acc, r) => ((acc[r.bidder] ??= []).push(r), acc),
    {},
  );
  return (
    <div className="space-y-4">
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
      {detailed &&
        Object.entries(byBidder).map(([bidder, rows]) => (
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
    </div>
  );
}
