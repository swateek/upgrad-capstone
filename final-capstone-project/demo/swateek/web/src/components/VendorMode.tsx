"use client";

import { useState } from "react";
import { api, isError, type ScreeningResult } from "@/lib/api";
import { Badge, Button, Callout, ErrorNote, Panel, Spinner, inputCls } from "./ui";

export function VendorMode() {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ScreeningResult | null>(null);

  async function screen(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const r = await api.tool<ScreeningResult>("screen_vendor", { name: name.trim() });
      if (isError(r.result)) setError(r.result.error);
      else setResult(r.result);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <Panel>
        <form onSubmit={screen} className="flex flex-wrap items-end gap-3">
          <div className="min-w-64 flex-1">
            <label className="mb-1 block text-sm font-medium" htmlFor="vendor">
              Firm or brand name
            </label>
            <input
              id="vendor"
              className={inputCls}
              placeholder="e.g. Prama Hikvision India Pvt. Ltd."
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <Button type="submit" disabled={busy || name.trim().length < 2}>
            Screen
          </Button>
          {busy && <Spinner label="Checking the loaded lists…" />}
        </form>
        <p className="mt-3 text-xs text-muted">
          Matching is done in code against dated snapshots. The assistant never decides a match, and
          absence from a snapshot is not a finding that a firm is eligible.
        </p>
      </Panel>

      {error && <ErrorNote message={error} />}

      {result && (
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
      )}
    </div>
  );
}
