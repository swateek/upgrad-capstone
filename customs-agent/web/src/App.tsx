import { useCallback, useEffect, useRef, useState } from "react";
import { ask } from "./api";
import { AnswerSlip } from "./AnswerSlip";
import { RegulationPanel } from "./RegulationPanel";
import type { AskResponse, Mode } from "./types";

interface Turn {
  id: number;
  question: string;
  shown: string; // what the traveller typed this turn
  response?: AskResponse;
  error?: string;
}

const EXAMPLES = [
  "4 bottles of wine after 10 days in Italy, 750 ml, 13%, $30 each. I'm 34, first trip this year. Do I owe anything?",
  "Day trip to Tijuana. I'm 33. One 750 ml bottle of tequila, 40%, $25. What do I owe?",
  "A box of 10 Cuban cigars bought in Cancún. I'm 45, back after 5 days. Can I bring them?",
];

export default function App() {
  const [question, setQuestion] = useState("");
  const [mode, setMode] = useState<Mode>("planner");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [cite, setCite] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const nextId = useRef(1);

  const run = useCallback(
    async (full: string, shown: string) => {
      const id = nextId.current++;
      setTurns((t) => [...t, { id, question: full, shown }]);
      setBusy(true);
      try {
        const response = await ask(full, mode);
        setTurns((t) => t.map((x) => (x.id === id ? { ...x, response } : x)));
      } catch (e) {
        setTurns((t) => t.map((x) => (x.id === id ? { ...x, error: (e as Error).message } : x)));
      } finally {
        setBusy(false);
      }
    },
    [mode],
  );

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "end" });
  }, [turns]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const q = question.trim();
    if (!q || busy) return;
    setQuestion("");
    run(q, q);
  };

  return (
    <div className={`page ${cite ? "page--reading" : ""}`}>
      <header className="top">
        <p className="brand">DeclareRight</p>
        <p className="top__note">Duty estimates for US residents bringing alcohol or tobacco home</p>
      </header>

      <main className={`main ${turns.length === 0 ? "main--empty" : ""}`}>
        <div className="thread">
          {turns.length === 0 && (
            <section className="intro">
              <h1>What are you bringing home?</h1>
              <p>
                Describe the bottles or tobacco, where you bought them, how long you were away and your age. You get what you would
                owe, how it was worked out and the rules it rests on.
              </p>
            </section>
          )}

          {turns.map((t) => (
            <div key={t.id} className="turn">
              <p className="turn__q">{t.shown}</p>
              {t.response && (
                <AnswerSlip
                  response={t.response}
                  onCite={setCite}
                  busy={busy}
                  onAnswerClarify={(reply) =>
                    // interim, until LangGraph sessions (Days 8-9): re-ask with the question and its answer
                    run(`${t.question}\nAsked: ${(t.response!.card.clarify ?? []).join(" ")}\nAnswer: ${reply}`, reply)
                  }
                />
              )}
              {!t.response && !t.error && (
                <div className="working-on" role="status">
                  <span className="working-on__bar" aria-hidden="true" />
                  Checking restrictions, then your exemption, then duty. This takes about ten seconds.
                </div>
              )}
              {t.error && <p className="turn__error">{t.error}</p>}
            </div>
          ))}
          <div ref={endRef} />
        </div>

        <form className="ask" onSubmit={submit}>
          <label htmlFor="q" className="sr-only">
            Your question
          </label>
          <textarea
            id="q"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) submit(e);
            }}
            placeholder="For example: 3 bottles of rum from Jamaica, 1 litre each, $22 a bottle. I'm 46, back after a week."
            rows={3}
            disabled={busy}
          />
          <div className="ask__row">
            {turns.length === 0 && (
              <div className="examples">
                {EXAMPLES.map((x) => (
                  <button type="button" key={x} className="example" onClick={() => setQuestion(x)}>
                    {x.split(".")[0]}
                  </button>
                ))}
              </div>
            )}
            <fieldset className="mode">
              <legend className="sr-only">How the tools are chosen</legend>
              <label>
                <input type="radio" name="mode" checked={mode === "planner"} onChange={() => setMode("planner")} />
                Model plans
              </label>
              <label>
                <input type="radio" name="mode" checked={mode === "router"} onChange={() => setMode("router")} />
                Fixed plan
              </label>
            </fieldset>
            <button type="submit" className="ask__go" disabled={busy || !question.trim()}>
              {busy ? "Working it out" : "Check my items"}
            </button>
          </div>
        </form>
      </main>

      {cite && <RegulationPanel citationId={cite} onClose={() => setCite(null)} />}
    </div>
  );
}
