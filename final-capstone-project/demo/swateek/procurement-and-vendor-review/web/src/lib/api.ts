// Typed client for the backend (through the /api proxy).

export type DomainInfo = {
  name: string;
  display_name: string;
  ui_modes: string[];
  tools: { name: string; description: string; ui_mode: string | null }[];
  instruments: string[];
  draft_notice: string;
};

export type Hit = {
  citation: string;
  doc_id: string;
  title: string;
  instrument: string;
  edition_date: string | null;
  part: number;
  synthetic: boolean;
  score: number;
  text: string;
};

export type AnswerResult = {
  question: string;
  answer: string;
  citations: string[];
  uncited_sentences: string[];
  invalid_handles: string[];
  hits: Hit[];
  latency_s: number;
};

export type ScreeningList = {
  list: string;
  title: string;
  synthetic: boolean;
  snapshot_date: string;
  status: "present" | "not_present";
  matches: { supplier_name: string; brand: string; category: string; period: string | null; debarring_entity: string | null }[];
  matched_rows: number;
  history_versions: string[];
  possible_matches: { listed_name: string; reason: string }[];
  source_url: string | null;
  scope: string | null;
  disclaimer: string | null;
};

export type ScreeningResult = {
  query: string;
  normalized_query: string;
  status: "present" | "not_present";
  statement: string;
  lists: ScreeningList[];
};

export type ScoreRow = {
  bidder: string;
  requirement_id: string;
  requirement: string;
  kind: "mandatory" | "scored";
  weight: number | null;
  quoted_evidence: string | null;
  score: number | "pass" | "fail" | null;
  gap: string | null;
};

export type Bidder = {
  bidder: string;
  name: string;
  status: "responsive" | "non_responsive" | "withheld_screening";
  failed_mandatory: string[];
  technical_total: number | null;
  quoted_price_inr: number | null;
  price_gap: string | null;
  screening: {
    status: string;
    statement: string;
    hits: { list: string; snapshot_date: string; synthetic: boolean }[];
    history_versions: string[];
    possible_matches: string[];
  };
};

export type ScoreSheet = {
  case_id: string;
  title: string;
  draft_notice: string;
  rows: ScoreRow[];
  bidders: Bidder[];
  ranking_eligible: string[];
  withheld_bidders: { bidder: string; name: string }[];
};

export type ToolError = { error: string; refusal_rule?: string; details?: unknown };

export type CaseListing = {
  case_id: string;
  title: string;
  procurement_type: string;
  has_requirement_sheet: boolean;
};

async function call<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api/${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(typeof data?.detail === "string" ? data.detail : `Request failed (${res.status})`);
  }
  return data as T;
}

export const api = {
  domain: () => call<DomainInfo>("domain"),
  cases: () => call<CaseListing[]>("listings/bid-cases"),
  answer: (question: string, instrument?: string) =>
    call<AnswerResult>("answer", { question, instrument: instrument || null }),
  tool: <T>(name: string, args: Record<string, unknown>) =>
    call<{ tool: string; is_draft: boolean; result: T | ToolError }>(`tools/${name}`, args),
};

export function isError(x: unknown): x is ToolError {
  return typeof x === "object" && x !== null && "error" in x;
}
