// While the agent works: "queued" if another question holds the shared model, then each
// step as it starts. Nothing of the answer is shown until the verifier has passed it.

export type ProgressState = { queued: boolean; steps: string[] };

export function Progress({ state }: { state: ProgressState }) {
  const current = state.steps.at(-1);
  return (
    <div
      className="rounded-2xl border border-line bg-surface px-5 py-4"
      role="status"
      aria-live="polite"
    >
      <div className="flex items-center gap-3 text-sm">
        <span className="relative flex size-2.5">
          <span className="absolute inline-flex size-full animate-ping rounded-full bg-accent opacity-50" />
          <span className="relative inline-flex size-2.5 rounded-full bg-accent" />
        </span>
        <span className="text-ink">
          {state.queued && state.steps.length === 0
            ? "Queued: the model is answering someone else. You're next."
            : (current ?? "Starting…")}
        </span>
      </div>
      {state.steps.length > 1 && (
        <ol className="mt-3 space-y-1 border-l border-line pl-4 text-xs text-muted">
          {state.steps.slice(0, -1).map((s, i) => (
            <li key={`${s}-${i}`}>{s}</li>
          ))}
        </ol>
      )}
    </div>
  );
}
