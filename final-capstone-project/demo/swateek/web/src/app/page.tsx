"use client";

import { useEffect, useState } from "react";
import { api, type DomainInfo } from "@/lib/api";
import { BidMode } from "@/components/BidMode";
import { PolicyMode } from "@/components/PolicyMode";
import { VendorMode } from "@/components/VendorMode";
import { Badge, ErrorNote, Spinner } from "@/components/ui";

const MODE_LABELS: Record<string, string> = {
  policy: "Policy Q&A",
  vendor: "Vendor screening",
  bid: "Bid comparison",
};

export default function Home() {
  const [domain, setDomain] = useState<DomainInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState("policy");

  useEffect(() => {
    api
      .domain()
      .then((d) => {
        setDomain(d);
        setMode(d.ui_modes[0] ?? "policy");
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  return (
    <main className="relative mx-auto max-w-5xl px-4 py-8 sm:px-6">
      <header className="relative z-10 mb-6">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold tracking-tight">{domain?.display_name ?? "Copilot"}</h1>
          <Badge tone="warn">DRAFT · decision support only</Badge>
        </div>
        <p className="mt-2 text-sm text-muted">
          {domain?.draft_notice ??
            "All output is a draft for a human decision-maker. This system does not award, place orders, or debar."}
        </p>
      </header>

      {error && <ErrorNote message={`Could not reach the API: ${error}`} />}
      {!domain && !error && <Spinner label="Loading…" />}

      {domain && (
        <>
          <nav className="relative z-10 mb-5 flex gap-1 rounded-xl border border-line bg-panel p-1" role="tablist">
            {domain.ui_modes.map((m) => (
              <button
                key={m}
                role="tab"
                aria-selected={mode === m}
                onClick={() => setMode(m)}
                className={`flex-1 rounded-lg px-3 py-2 text-sm font-medium transition ${
                  mode === m ? "bg-accent text-white dark:text-bg" : "text-muted hover:bg-bg"
                }`}
              >
                {MODE_LABELS[m] ?? m}
              </button>
            ))}
          </nav>
          {/* keep each mode mounted so results survive tab switches */}
          <div hidden={mode !== "policy"}>
            <PolicyMode instruments={domain.instruments} />
          </div>
          <div hidden={mode !== "vendor"}>
            <VendorMode />
          </div>
          <div hidden={mode !== "bid"}>
            <BidMode />
          </div>
        </>
      )}

      <footer className="relative z-10 mt-10 border-t border-line pt-4 text-xs text-muted">
        Synthetic bid cases and the buyer-specific list are labelled samples. Screening snapshots are dated;
        check the date on every result.
      </footer>
    </main>
  );
}
