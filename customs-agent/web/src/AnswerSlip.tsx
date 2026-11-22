import { useState } from "react";
import { LINE_TEXT, headline, money, splitFact } from "./format";
import type { AskResponse } from "./types";

interface Props {
  response: AskResponse;
  onCite: (id: string) => void;
  onAnswerClarify: (text: string) => void;
  busy: boolean;
}

export function AnswerSlip({ response: r, onCite, onAnswerClarify, busy }: Props) {
  const h = headline(r);
  const c = r.card;
  const [reply, setReply] = useState("");

  return (
    <article className={`slip slip--${h.tone}`} aria-live="polite">
      <header className="slip__band">
        <h2 className="slip__title">{h.title}</h2>
        {h.sub && <p className="slip__sub">{h.sub}</p>}
      </header>

      <div className="slip__body">
        {c.items && c.items.length > 0 && (
          <table className="slip__items">
            <caption className="sr-only">Result for each item</caption>
            <tbody>
              {c.items.map((i) => (
                <tr key={i.line} className={`row row--${i.type}`}>
                  <th scope="row">{i.item}</th>
                  <td>{LINE_TEXT[i.type]}</td>
                  <td className="num">{i.owed_usd ? money(i.owed_usd) : i.type === "nothing_to_pay" ? money(0) : ""}</td>
                </tr>
              ))}
            </tbody>
            {r.answer?.total_usd != null && r.answer.total_usd > 0 && (
              <tfoot>
                <tr>
                  <th scope="row">Total</th>
                  <td className="muted">
                    Duty {money(r.answer.duty_usd ?? 0)}, federal excise {money(r.answer.excise_usd ?? 0)}
                  </td>
                  <td className="num">{money(r.answer.total_usd)}</td>
                </tr>
              </tfoot>
            )}
          </table>
        )}

        {c.explanation ? (
          <p className="slip__lede">{c.explanation}</p>
        ) : (
          r.answer?.message &&
          r.outcome !== "answered" &&
          r.outcome !== "clarify" && <p className="slip__lede">{r.answer.message}</p>
        )}

        {r.outcome === "clarify" && (
          <form
            className="clarify"
            onSubmit={(e) => {
              e.preventDefault();
              if (reply.trim()) onAnswerClarify(reply.trim());
            }}
          >
            <p className="slip__lede">To work this out I need:</p>
            <ul className="clarify__qs">
              {(c.clarify ?? []).map((q) => (
                <li key={q}>{q}</li>
              ))}
            </ul>
            <label htmlFor="clarify-reply">Your answer</label>
            <div className="clarify__row">
              <input
                id="clarify-reply"
                value={reply}
                onChange={(e) => setReply(e.target.value)}
                placeholder="e.g. I'm 41, back after 4 days, first trip this year"
                disabled={busy}
              />
              <button type="submit" disabled={busy || !reply.trim()}>
                Send answer
              </button>
            </div>
          </form>
        )}

        {c.working && c.working.length > 0 && (
          <details className="slip__section" open>
            <summary>How it was worked out</summary>
            <ol className="working">
              {c.working.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ol>
          </details>
        )}

        {c.facts_relied_on && c.facts_relied_on.length > 0 && (
          <section className="slip__section">
            <h3>What this assumes about you</h3>
            <dl className="facts">
              {c.facts_relied_on.map((f) => {
                const [k, v] = splitFact(f);
                return (
                  <div key={f} className="fact">
                    <dt>{k}</dt>
                    <dd>{v}</dd>
                  </div>
                );
              })}
            </dl>
            <p className="hint">If any of these is wrong, ask again with the right detail.</p>
          </section>
        )}

        {c.citations && c.citations.length > 0 && (
          <section className="slip__section">
            <h3>Rules behind this answer</h3>
            <ul className="cites">
              {c.citations.map((x) => (
                <li key={x.id}>
                  <button className="cite" onClick={() => onCite(x.id)}>
                    <span className="cite__label">{x.label}</span>
                    {x.as_of && <span className="cite__date">as of {x.as_of}</span>}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>

      <footer className="slip__foot">
        <p className="slip__disclaimer">{c.disclaimer ?? "Estimate only. The CBP officer decides. Declare everything."}</p>
        <p className="slip__meta">
          <span>{r.cost.model_calls} model calls</span>
          <span>{r.cost.tokens.toLocaleString()} tokens</span>
          <span>{r.cost.tool_steps} tool steps</span>
          <span>{r.cost.seconds} s</span>
          {r.trace.url ? (
            <a href={r.trace.url} target="_blank" rel="noreferrer">
              View trace
            </a>
          ) : (
            r.trace.id && <span title={r.trace.id}>Trace saved to logs/trace.jsonl</span>
          )}
        </p>
      </footer>
    </article>
  );
}
