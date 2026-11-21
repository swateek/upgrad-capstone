import type { ReactNode } from "react";

export function Panel({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <section className={`relative z-10 rounded-xl border border-line bg-panel p-5 shadow-sm ${className}`}>
      {children}
    </section>
  );
}

type Tone = "neutral" | "ok" | "warn" | "bad" | "accent";
const tones: Record<Tone, string> = {
  neutral: "bg-bg text-muted border-line",
  ok: "bg-ok-soft text-ok border-ok/30",
  warn: "bg-warn-soft text-warn border-warn/30",
  bad: "bg-bad-soft text-bad border-bad/30",
  accent: "bg-accent-soft text-accent border-accent/30",
};

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: Tone }) {
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${tones[tone]}`}>
      {children}
    </span>
  );
}

export function Callout({ children, tone = "warn" }: { children: ReactNode; tone?: Tone }) {
  return <div className={`rounded-lg border px-4 py-3 text-sm ${tones[tone]}`}>{children}</div>;
}

export function Button(props: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50 dark:text-bg"
    />
  );
}

export const inputCls =
  "w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm outline-none focus:border-accent focus:ring-2 focus:ring-accent/20";

export function Spinner({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-muted" role="status">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-line border-t-accent" />
      {label}
    </div>
  );
}

export function ErrorNote({ message }: { message: string }) {
  return <Callout tone="bad">{message}</Callout>;
}

export const inr = (n: number | null) =>
  n === null ? "—" : `Rs ${n.toLocaleString("en-IN")}`;
