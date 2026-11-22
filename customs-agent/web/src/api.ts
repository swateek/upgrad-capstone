import type { AskResponse, ClauseText, Mode } from "./types";

async function json<T>(res: Response): Promise<T> {
  if (res.ok) return res.json() as Promise<T>;
  let detail = `The server answered ${res.status}.`;
  try {
    const body = await res.json();
    if (typeof body.detail === "string") detail = body.detail;
  } catch {
    /* not JSON */
  }
  throw new Error(detail);
}

export async function ask(question: string, mode: Mode, sessionId?: string): Promise<AskResponse> {
  const res = await fetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, mode, session_id: sessionId }),
  });
  return json<AskResponse>(res);
}

export async function clause(citationId: string): Promise<ClauseText> {
  return json<ClauseText>(await fetch(`/api/clause/${encodeURIComponent(citationId)}`));
}
