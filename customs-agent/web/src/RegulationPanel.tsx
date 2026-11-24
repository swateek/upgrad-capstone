import { useEffect, useRef, useState } from "react";
import { clause } from "./api";
import type { ClauseText } from "./types";

export function RegulationPanel({ citationId, onClose }: { citationId: string; onClose: () => void }) {
  const [data, setData] = useState<ClauseText | null>(null);
  const [error, setError] = useState<string | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    let live = true;
    setData(null);
    setError(null);
    clause(citationId)
      .then((d) => live && setData(d))
      .catch((e: Error) => live && setError(e.message));
    closeRef.current?.focus();
    return () => {
      live = false;
    };
  }, [citationId]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <aside className="reg" aria-label="Regulation text">
      <div className="reg__bar">
        <p className="reg__label">{data?.label ?? citationId}</p>
        <button ref={closeRef} className="reg__close" onClick={onClose}>
          Close
        </button>
      </div>
      {error && <p className="reg__error">{error}</p>}
      {!data && !error && <p className="reg__muted">Loading the text…</p>}
      {data && (
        <>
          <h2 className="reg__title">{data.title}</h2>
          <p className="reg__meta">
            {data.as_of && <span>Text as of {data.as_of}</span>}
            {data.source_url && (
              <a href={data.source_url} target="_blank" rel="noreferrer">
                Open the official source
              </a>
            )}
          </p>
          <div className="reg__body">
            {data.sections.map((s, i) => (
              <section key={i}>
                {s.heading && <h3>{s.heading.split(" > ").pop()}</h3>}
                <p>{stripHeading(s.text, s.heading)}</p>
              </section>
            ))}
          </div>
        </>
      )}
    </aside>
  );
}

/** Chunks repeat their heading path as the first line; the viewer shows it once, as a heading. */
function stripHeading(text: string, heading: string): string {
  return heading && text.startsWith(heading) ? text.slice(heading.length).trim() : text;
}
