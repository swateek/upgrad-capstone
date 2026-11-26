import type { AskResponse, ClauseText, Mode } from "./types";

/** The hosted app needs an access code: any API call can answer 401 until it is entered. */
export class AccessNeeded extends Error {}

async function json<T>(res: Response): Promise<T> {
  if (res.ok) return res.json() as Promise<T>;
  let detail = `The server answered ${res.status}.`;
  try {
    const body = await res.json();
    if (typeof body.detail === "string") detail = body.detail;
  } catch {
    /* not JSON */
  }
  if (res.status === 401) throw new AccessNeeded(detail);
  throw new Error(detail);
}

export async function accessStatus(): Promise<{ required: boolean; ok: boolean }> {
  return json(await fetch("/api/access"));
}

export async function unlock(code: string): Promise<void> {
  await json(
    await fetch("/api/access", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code }),
    }),
  );
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

export async function edit(sessionId: string, field: string, value: unknown, mode: Mode): Promise<AskResponse> {
  const res = await fetch("/api/edit", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, field, value, mode }),
  });
  return json<AskResponse>(res);
}
