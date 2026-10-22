"use client";

import Link from "next/link";
import { useState } from "react";
import styles from "../ask/ask.module.css";

const REPORT = "600276-2026H1";
const QUESTION = "revenue_rows_two_scopes_2026H1";
const SOURCE = {
  documentId: "600276-2026H1-cninfo-1225483600",
  url: "https://static.cninfo.com.cn/finalpage/2026-08-20/1225483600.PDF",
  sourceSha: "ff6910663a9726acb889aa061a8bab1433f58890d81ebea013b8c637a097a7aa",
  canonicalSha: "96784f9deba244aab85bd117b9a1894bdcbd689a8368554f84014703f1e8b864",
} as const;

const SCOPES = [
  {kind: "consolidated_income_statement", title: "合并利润表", row: "其中：营业收入"},
  {kind: "parent_income_statement", title: "母公司利润表", row: "一、营业收入"},
] as const;

type Claim = {
  claim_id: string; kind: string; evidence_id: string;
  source_page: number; statement_kind_candidate: string;
  statement_title: string; row_label: string; column_header: string;
  value_verbatim: string; text: string;
};
type Review = {
  claim_id: string; evidence_id: string; verdict: string;
  review_scope: string; financial_semantic_review: string;
};
type Answer = {
  status: string; question_code: string; report_key: string;
  document_id: string; source_url: string; source_sha256: string;
  canonical_sha256: string; source_report_id: string; llm_draft_id: string;
  model: string; brief: string; claims: Claim[]; reviews: Review[];
  research_publication: string; financial_semantic_review: string;
  usage: {total_tokens: number; estimated_cost_usd_low: string;
    estimated_cost_usd_high: string};
};
function qualified(a: Answer | null): a is Answer {
  if (!a || a.status !== "LLM_MULTI_EVIDENCE_PACKET_MATCHED" ||
      a.question_code !== QUESTION || a.report_key !== REPORT ||
      a.document_id !== SOURCE.documentId || a.source_url !== SOURCE.url ||
      a.source_sha256 !== SOURCE.sourceSha ||
      a.canonical_sha256 !== SOURCE.canonicalSha ||
      a.model !== "deepseek-flash" ||
      a.research_publication !== "BLOCKED" ||
      a.financial_semantic_review !== "NOT_PERFORMED" ||
      !/^[a-f0-9]{64}$/.test(a.source_report_id) ||
      !/^[a-f0-9]{64}$/.test(a.llm_draft_id) ||
      !Array.isArray(a.claims) || a.claims.length !== 2 ||
      !Array.isArray(a.reviews) || a.reviews.length !== 2 ||
      !a.usage || !Number.isInteger(a.usage.total_tokens) ||
      a.usage.total_tokens <= 0 ||
      typeof a.brief !== "string" ||
      a.brief !== "The disclosure has separate revenue-labelled rows in its consolidated and parent-company income-statement sections. These are two distinct source observations, not a comparison or a conclusion about their accounting relationship.") return false;
  if (a.claims[0].evidence_id === a.claims[1].evidence_id) return false;
  return a.claims.every((c, i) => {
    const s = SCOPES[i];
    const r = a.reviews[i];
    return c.claim_id === `DS${i+1}` && c.kind === "OBSERVED_FACT" &&
      c.statement_kind_candidate === s.kind &&
      c.statement_title.replace(/\s/g, "") === s.title &&
      c.row_label.replace(/\s/g, "") === s.row &&
      c.column_header.replace(/\s/g, "") === "2026年半年度" &&
      /^[0-9,]+\.[0-9]{2}$/.test(c.value_verbatim) &&
      typeof c.evidence_id === "string" && c.evidence_id.length > 0 &&
      Number.isInteger(c.source_page) && c.source_page > 0 &&
      c.text === `In the source section "${c.statement_title}", the row "${c.row_label}" under "${c.column_header}" reads "${c.value_verbatim}".` &&
      r.claim_id === c.claim_id && r.evidence_id === c.evidence_id &&
      r.verdict === "LITERAL_LOCATION_MATCH_ONLY" &&
      r.review_scope === "NATIVE_PDF_TEXT_AND_EXACT_LLM_BINDING" &&
      r.financial_semantic_review === "NOT_PERFORMED";
  });
}

export default function TwoSourceBrief() {
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function ask() {
    if (busy) return;
    setBusy(true); setAnswer(null); setError("");
    try {
      const res = await fetch("/api/local-source-answer", {
        method: "POST", headers: {"content-type": "application/json"},
        cache: "no-store",
        body: JSON.stringify({report_key: REPORT, question_code: QUESTION}),
      });
      if (!res.ok) throw new Error("LOCAL_UNAVAILABLE");
      const packet = (await res.json()) as Answer;
      if (!qualified(packet)) throw new Error("UNQUALIFIED_PACKET");
      setAnswer(packet);
    } catch {
      setError("Both reviewed source observations and the exact model proposal are required. The briefing was withheld; no financial answer was released.");
    } finally {
      setBusy(false);
    }
  }
  return <main className={styles.page}><div className={styles.shell}>
    <header className={styles.top}><span className={styles.brand}>FR / FINANCIAL RESEARCH</span>
      <Link className={styles.back} href="/research/source-workspace/ask">← Source-bound questions</Link></header>
    <section className={styles.hero}><p className={styles.kicker}>M1.8A / LOCAL TWO-SOURCE BRIEF</p>
      <h1>Two pieces of evidence. One bounded brief.</h1>
      <p>恒瑞医药 · 2026 H1 · Independent literal-location checks before a single explicit DeepSeek request. Each source observation gets its own claim, review and original PDF citation.</p>
    </section>
    <div className={styles.grid}>
      <section className={styles.panel} aria-label="Two-source research briefing">
        <p className={styles.section}>SUPPORTED QUESTION</p>
        <div className={styles.question}>What revenue-labelled source rows appear in the consolidated and parent-company income statements of Hengrui&apos;s 2026 H1 disclosure?</div>
        <button type="button" className={styles.button} disabled={busy} onClick={ask}>
          {busy ? "Checking both source cells and requesting model…" : "Draft two-source brief · one paid call"}
        </button>
        <p className={styles.note}>Only 恒瑞医药 is supported for this slice. One explicit paid request; no automatic retries. Maximum four attempts per local server session.</p>
      </section>
      <aside className={styles.aside}><p className={styles.section}>PUBLICATION BOUNDARY</p>
        <h2>Source structure, not an investment conclusion.</h2>
        <div className={styles.item}><strong>Research publication</strong> BLOCKED — always</div>
        <div className={styles.item}><strong>Financial-semantic review</strong> NOT PERFORMED</div>
        <div className={styles.item}><strong>Permitted output</strong> Two source-text observations. No derived differences, ratios, growth, causal explanation, valuation or trade recommendation.</div>
      </aside>
    </div>
    {error && <section className={styles.result} role="alert"><h2>Briefing withheld</h2><p className={styles.warn}>{error}</p></section>}
    {answer && qualified(answer) && <section className={styles.result} aria-live="polite">
      <p className={styles.section}>SOURCE-BOUND RESEARCH BRIEF · UNPUBLISHED</p>
      <h2>恒瑞医药 · Two independently matched claims</h2>
      <p>{answer.brief}</p>
      {answer.claims.map((c, i) => <div key={c.claim_id} className={styles.claim}>
        <p className={styles.section}>CLAIM {i+1} · {c.claim_id} · {SCOPES[i].title}</p>
        <p>{c.text}</p>
        <p className={styles.muted}>Evidence ID: {c.evidence_id}</p>
        <p className={styles.muted}>Independent review: {answer.reviews[i].verdict} · Financial semantics: NOT PERFORMED</p>
        <a className={styles.source} target="_blank" rel="noopener noreferrer"
          href={`${SOURCE.url}#page=${c.source_page}`}>Open original PDF · Page {c.source_page} ↗</a>
      </div>)}
      <p className={styles.muted}>Model: {answer.model} · Tokens: {answer.usage.total_tokens} · Estimated cost: US${answer.usage.estimated_cost_usd_low}–${answer.usage.estimated_cost_usd_high}</p>
      <p className={styles.warn}>Literal evidence matches only. No independent accounting qualification. Research publication BLOCKED.</p>
    </section>}
    <p className={styles.note}>Local developer experiment · API key remains on the backend</p>
  </div></main>;
}
