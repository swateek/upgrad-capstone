// Typed client for the backend (through the /api proxy). Questions stream progress as
// server-sent events: queued?, started, node*, then card (or error).

export type Outcome = "answered" | "clarify" | "refused" | "out_of_scope" | "escalated";

export type Figure = {
  handle: string;
  name: string;
  label: string;
  value: string;
  unit: string;
  display: string;
};

export type Source = {
  handle?: string;
  clause_id: string;
  citation: string;
  url: string | null;
  retrieved?: boolean;
};

export type Card = {
  outcome: Outcome;
  kind: string;
  bottom_line: string;
  working: string[];
  facts_relied_on: { label: string; value: string }[];
  notes: { id: string; text: string }[];
  sources: Source[];
  figures: Figure[];
  owe_usd: string | null;
  exemption_usd: number | null;
  clarify_question: string | null;
  clarify_fields: string[];
  handoff: Record<string, unknown> | null;
  as_of: string;
  disclaimer: string;
  meta: {
    cached?: boolean;
    model_calls?: number;
    seconds?: number;
    escalation?: string;
    [k: string]: unknown;
  };
};

export type Facts = {
  profile: Record<string, unknown>;
  basket: Record<string, unknown>[];
};

export type Thread = { thread_id: string; facts: Facts | null; card: Card | null };

export type StreamEvent =
  | { event: "queued" }
  | { event: "started" }
  | { event: "node"; node: string; label: string }
  | { event: "card"; thread_id: string; card: Card }
  | { event: "error"; detail: string };

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

async function detail(res: Response): Promise<string> {
  try {
    const body = await res.json();
    return typeof body.detail === "string" ? body.detail : "Something went wrong.";
  } catch {
    return "Something went wrong.";
  }
}

/** POST a question (or a facts edit) and call onEvent for every streamed event. */
export async function stream(
  path: string,
  body: unknown,
  onEvent: (e: StreamEvent) => void,
): Promise<void> {
  const res = await fetch(`/api/${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok || !res.body) throw new ApiError(await detail(res), res.status);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let cut: number;
    while ((cut = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 2);
      const data = block
        .split("\n")
        .filter((l) => l.startsWith("data: "))
        .map((l) => l.slice(6))
        .join("");
      if (data) onEvent(JSON.parse(data) as StreamEvent);
    }
  }
}

export async function getThread(id: string): Promise<Thread | null> {
  const res = await fetch(`/api/threads/${id}`, { cache: "no-store" });
  if (res.status === 404) return null;
  if (!res.ok) throw new ApiError(await detail(res), res.status);
  return (await res.json()) as Thread;
}

export type Health = {
  status: string;
  version: string;
  agent: string | null;
  mode: string;
  endpoints: string;
};

export async function getHealth(): Promise<Health> {
  const res = await fetch("/api/health", { cache: "no-store" });
  if (!res.ok) throw new ApiError("The API is not reachable.", res.status);
  return (await res.json()) as Health;
}
