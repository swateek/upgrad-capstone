"use client";

import { useState } from "react";
import { api, isError, type ScreeningResult } from "@/lib/api";
import { ScreeningCard } from "./results";
import { Button, ErrorNote, Panel, Spinner, inputCls } from "./ui";

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
      {result && <ScreeningCard result={result} />}
    </div>
  );
}
