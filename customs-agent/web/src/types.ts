export type Outcome = "answered" | "clarify" | "refused" | "escalated";

export type LineType =
  | "owe"
  | "nothing_to_pay"
  | "prohibited"
  | "declare_detention_risk"
  | "relinquish_excess";

export interface Item {
  line: number;
  item: string;
  type: LineType;
  owed_usd: number | null;
}

export interface Citation {
  id: string;
  label: string;
  as_of: string | null;
  url: string | null;
}

export interface Card {
  bottom_line?: string;
  items?: Item[];
  explanation?: string;
  working?: string[];
  facts_relied_on?: string[];
  citations?: Citation[];
  disclaimer?: string;
  clarify?: string[];
  state_flag?: { state: string; name: string; note: string; source: string } | null;
}

export interface Answer {
  outcome: Outcome;
  total_usd: number | null;
  duty_usd: number | null;
  excise_usd: number | null;
  whatif: { max_units: number; owed_usd: number } | null;
  clarify_facts: string[];
  citations: string[];
  message: string;
}

export interface AskResponse {
  session_id: string;
  outcome: Outcome;
  reason: string | null;
  answer: Answer | null;
  card: Card;
  trace: { id: string | null; url: string | null };
  cost: { tool_steps: number; model_calls: number; tokens: number; seconds: number };
  error: boolean;
}

export interface ClauseText {
  citation_id: string;
  label: string;
  title: string;
  authority: string;
  source_url: string | null;
  as_of: string | null;
  sections: { heading: string; text: string }[];
}

export type Mode = "planner" | "router";
