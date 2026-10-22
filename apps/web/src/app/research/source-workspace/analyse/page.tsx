"use client";

import Link from "next/link";
import { useState } from "react";
import styles from "../ask/ask.module.css";

const REPORT = "600276-2026H1";
const QUESTION = "management_innovation_source_context_2026H1";
const SOURCE = {
  documentId: "600276-2026H1-cninfo-1225483600",
  url: "https://static.cninfo.com.cn/finalpage/2026-08-20/1225483600.PDF",
  sourceSha: "ff6910663a9726acb889aa061a8bab1433f58890d81ebea013b8c637a097a7aa",
  canonicalSha: "96784f9deba244aab85bd117b9a1894bdcbd689a8368554f84014703f1e8b864",
} as const;
const EXPECTED = [
  {id: "F1", kind: "SOURCE_FACT", source: "consolidated_income_statement", label: "合并利润表", row: "其中：营业收入"},
  {id: "F2", kind: "SOURCE_FACT", source: "parent_income_statement", label: "母公司利润表", row: "一、营业收入"},
  {id: "M1", kind: "MANAGEMENT_STATEMENT", source: "MANAGEMENT_DISCUSSION_PASSAGE", label: "Management discussion", row: "创新药销售收入"},
] as const;

type Claim = {claim_id:string;kind:string;evidence_id:string;source_page:number;text:string;source_kind:string};
type Review = {claim_id:string;evidence_id:string|null;verdict:string;review_scope:string;financial_semantic_review:string};
type Answer = {
  status:string;question_code:string;report_key:string;document_id:string;
  source_url:string;source_sha256:string;canonical_sha256:string;
  source_report_id:string;llm_draft_id:string;model:string;
  claims:Claim[];reviews:Review[];inference_withheld_count:number;
  inference_supporting_claim_ids:string[];research_publication:string;
  financial_semantic_review:string;
  usage:{total_tokens:number;estimated_cost_usd_low:string;estimated_cost_usd_high:string};
};

function accepted(a: Answer | null): a is Answer {
  if (!a || a.status !== "LLM_MANAGEMENT_SOURCE_BOUND" ||
      a.report_key !== REPORT || a.question_code !== QUESTION ||
      a.document_id !== SOURCE.documentId || a.source_url !== SOURCE.url ||
      a.source_sha256 !== SOURCE.sourceSha || a.canonical_sha256 !== SOURCE.canonicalSha ||
      a.model !== "deepseek-flash" || a.research_publication !== "BLOCKED" ||
      a.financial_semantic_review !== "NOT_PERFORMED" ||
      !/^[a-f0-9]{64}$/.test(a.source_report_id) || !/^[a-f0-9]{64}$/.test(a.llm_draft_id) ||
      !Array.isArray(a.claims) || a.claims.length !== 3 ||
      !Array.isArray(a.reviews) || a.reviews.length !== 4 ||
      a.inference_withheld_count !== 1 ||
      JSON.stringify(a.inference_supporting_claim_ids) !== '["F1","F2","M1"]' ||
      !a.usage || !Number.isInteger(a.usage.total_tokens) || a.usage.total_tokens <= 0) return false;
  const ids = new Set(a.claims.map(c => c.evidence_id));
  if (ids.size !== 3) return false;
  if (!a.claims.every((c,i) => {
    const expected = EXPECTED[i];
    const review = a.reviews[i];
    if (!c || !review || c.claim_id !== expected.id || c.kind !== expected.kind ||
        c.source_kind !== expected.source || !/^[a-f0-9]{64}$/.test(c.evidence_id) ||
        !Number.isInteger(c.source_page) || c.source_page < 1 || c.source_page > 182 ||
        typeof c.text !== "string" || c.text.length > 400 ||
        review.claim_id !== c.claim_id || review.evidence_id !== c.evidence_id ||
        review.verdict !== "LITERAL_LOCATION_MATCH_ONLY" ||
        review.review_scope !== "INDEPENDENT_SOURCE_TEXT_AND_MODEL_BINDING" ||
        review.financial_semantic_review !== "NOT_PERFORMED") return false;
    if (i < 2) return c.text.includes(expected.label) && c.text.includes(expected.row) &&
      c.text.includes("2026 年半年度") && /^[\s\S]*reads "[0-9,]+\.[0-9]{2}"\.$/.test(c.text);
    return c.text.startsWith("The management discussion states (whitespace-normalized source excerpt): ") &&
      c.text.includes("创新药销售收入") && c.text.includes("比重达") &&
      c.text.endsWith("%。");
  })) return false;
  const hold = a.reviews[3];
  return hold.claim_id === "A1" && hold.evidence_id === null &&
    hold.verdict === "WITHHELD_UNQUALIFIED_INFERENCE" &&
    hold.review_scope === "FINANCIAL_SEMANTIC_REVIEW_NOT_AVAILABLE" &&
    hold.financial_semantic_review === "NOT_PERFORMED";
}

export default function SourceAndManagementContext() {
  const [answer, setAnswer] = useState<Answer|null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function requestBrief() {
    if (busy) return;
    setAnswer(null); setError(""); setBusy(true);
    try {
      const response = await fetch("/api/local-source-answer", {
        method: "POST", headers: {"content-type":"application/json"}, cache:"no-store",
        body: JSON.stringify({report_key:REPORT,question_code:QUESTION}),
      });
      if (!response.ok) throw new Error("LOCAL_UNAVAILABLE");
      const result = await response.json() as Answer;
      if (!accepted(result)) throw new Error("NOT_QUALIFIED");
      setAnswer(result);
    } catch {
      setError("The source or model proposal was not qualified. No source briefing or interpretation was released. Check local logs before trying again; this request may have consumed model tokens.");
    } finally { setBusy(false); }
  }
  return <main className={styles.page}><div className={styles.shell}>
    <header className={styles.top}><span className={styles.brand}>FR / FINANCIAL RESEARCH</span>
      <Link className={styles.back} href="/research/source-workspace/explain">← Two-source evidence</Link></header>
    <section className={styles.hero}>
      <p className={styles.kicker}>M1.8B / LOCAL SOURCE + MANAGEMENT</p>
      <h1>Facts, attribution, and a withheld inference.</h1>
      <p>恒瑞医药 · 2026 H1. Two income-statement observations plus one separately located management-discussion passage. A possible Analyst inference is recorded as withheld, never published as fact.</p>
    </section>
    <div className={styles.grid}>
      <section className={styles.panel} aria-label="Management source context question">
        <p className={styles.section}>BOUNDED RESEARCH QUESTION</p>
        <div className={styles.question}>What does the report state in its two revenue source rows and in its management discussion of innovative-drug sales? Which possible inference still requires review?</div>
        <button type="button" className={styles.button} disabled={busy} onClick={requestBrief}>
          {busy ? "Checking source passages and drafting…" : "Draft source-and-management note · one paid call"}
        </button>
        <p className={styles.note}>One issuer, three exact evidence bindings, one explicit paid DeepSeek call. Four total attempts per local API session; no automatic retry.</p>
      </section>
      <aside className={styles.aside}>
        <p className={styles.section}>REVIEW BOUNDARY</p>
        <h2>Three observations. No approved interpretation.</h2>
        <div className={styles.item}><strong>Source facts</strong> Literal cell matches only; no accounting meaning certified</div>
        <div className={styles.item}><strong>Management statement</strong> Attributed public-filing passage; not independently endorsed</div>
        <div className={styles.item}><strong>Analyst inference</strong> WITHHELD · financial-semantic review unavailable</div>
        <div className={styles.item}><strong>Research publication</strong> BLOCKED — always</div>
      </aside>
    </div>
    {error && <section className={styles.result} role="alert"><h2>Source note withheld</h2><p className={styles.warn}>{error}</p></section>}
    {answer && accepted(answer) && <section className={styles.result} aria-live="polite">
      <p className={styles.section}>UNPUBLISHED · THREE SOURCE-BOUND OBSERVATIONS</p>
      <h2>恒瑞医药 · Revenue source and management context</h2>
      <p>Two reported financial-statement cells and one management-discussion passage are shown separately. They do not establish a reconciliation, a performance explanation, or a causal relationship.</p>
      {answer.claims.map((c,i) => <article className={styles.claim} key={c.claim_id}>
        <p className={styles.section}>{c.claim_id} · {c.kind} · {EXPECTED[i].label}</p>
        <p>{c.text}</p>
        <p className={styles.muted}>Evidence: {c.evidence_id}</p>
        <p className={styles.muted}>Independent review: {answer.reviews[i].verdict} · Financial semantics NOT PERFORMED</p>
        <a className={styles.source} target="_blank" rel="noopener noreferrer"
          href={`${SOURCE.url}#page=${c.source_page}`}>Open original PDF · Page {c.source_page} ↗</a>
      </article>)}
      <div className={styles.claim}>
        <p className={styles.section}>A1 · ANALYST_INFERENCE</p>
        <p className={styles.warn}>WITHHELD_UNQUALIFIED_INFERENCE. A hypothesis was proposed but its text is not exposed. Claim-level financial-semantic review is not available.</p>
        <p className={styles.muted}>Proposed support: F1 · F2 · M1 · Verdict: {answer.reviews[3].verdict}</p>
      </div>
      <p className={styles.muted}>Model: {answer.model} · Tokens: {answer.usage.total_tokens} · Estimated cost: US${answer.usage.estimated_cost_usd_low}–${answer.usage.estimated_cost_usd_high}</p>
      <p className={styles.warn}>Literal-source checks only. Financial-semantic review NOT PERFORMED. Research publication BLOCKED.</p>
    </section>}
    <p className={styles.note}>Local developer experiment. No trading, no publication, and no model credential in the browser.</p>
  </div></main>;
}
