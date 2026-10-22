"use client";

import Link from "next/link";
import { useState } from "react";
import styles from "./ask.module.css";

const CATALOG = {
  "600276-2026H1": {
    name: "恒瑞医药", doc: "600276-2026H1-cninfo-1225483600",
    url: "https://static.cninfo.com.cn/finalpage/2026-08-20/1225483600.PDF",
    sourceSha: "ff6910663a9726acb889aa061a8bab1433f58890d81ebea013b8c637a097a7aa",
    canonicalSha: "96784f9deba244aab85bd117b9a1894bdcbd689a8368554f84014703f1e8b864",
  },
  "600760-2026H1": {
    name: "中航沈飞", doc: "600760-2026H1-cninfo-1225517994",
    url: "https://static.cninfo.com.cn/finalpage/2026-08-28/1225517994.PDF",
    sourceSha: "d53ee98c091fdcbb8df3ebcc3f8d9bef87f61b374615dc3165dadb594f637d99",
    canonicalSha: "620d3a30f73423527dd662e21ebf3367b546dfa6795c6fcf618f35ebf0008aa5",
  },
} as const;
type Report = keyof typeof CATALOG;
const QUESTION = "consolidated_revenue_2026H1";
type Answer = {
  status: string; report_key: string; question_code: string; question: string;
  document_id: string; source_url: string; source_sha256: string; canonical_sha256: string;
  source_report_id: string; llm_draft_id: string; model: string;
  research_publication: string; financial_semantic_review: string;
  claims: Array<{claim_id:string;evidence_id:string;source_page:number;statement_kind:string;
    row_label:string;column_header:string;value_verbatim:string;text:string;verification:string}>;
  usage: { prompt_tokens:number;completion_tokens:number;total_tokens:number;
    estimated_cost_usd_low:string;estimated_cost_usd_high:string};
};
function verified(a: Answer | null, report: Report): a is Answer {
  if (!a || a.status !== "LLM_PROPOSAL_PACKET_MATCHED" ||
      a.report_key !== report || a.question_code !== QUESTION ||
      a.document_id !== CATALOG[report].doc ||
      a.source_url !== CATALOG[report].url ||
      a.source_sha256 !== CATALOG[report].sourceSha ||
      a.canonical_sha256 !== CATALOG[report].canonicalSha ||
      a.model !== "deepseek-flash" ||
      a.research_publication !== "BLOCKED" ||
      a.financial_semantic_review !== "NOT_PERFORMED" ||
      !/^[a-f0-9]{64}$/.test(a.source_report_id) ||
      !/^[a-f0-9]{64}$/.test(a.llm_draft_id) ||
      !Array.isArray(a.claims) || a.claims.length !== 1 ||
      !a.usage || !Number.isInteger(a.usage.total_tokens)) return false;
  const c = a.claims[0];
  return c.claim_id === "DS1" && c.statement_kind === "consolidated_income_statement" &&
    c.verification === "EXACT_MATCH_TO_PREVERIFIED_LITERAL_PACKET" &&
    /^[0-9,]+\.[0-9]{2}$/.test(c.value_verbatim) &&
    Number.isInteger(c.source_page) && c.source_page > 0 &&
    typeof c.evidence_id === "string" && c.evidence_id.length > 0 &&
    typeof c.text === "string" && c.text.includes(c.value_verbatim) &&
    c.text.includes(c.row_label) && c.text.includes(c.column_header);
}
export default function AskLocalSource() {
  const [report, setReport] = useState<Report>("600276-2026H1");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [resultReport, setResultReport] = useState<Report>("600276-2026H1");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit() {
    if (busy) return;
    setBusy(true); setAnswer(null); setError(""); setResultReport(report);
    try {
      const response = await fetch("/api/local-source-answer", {
        method: "POST", headers: {"content-type": "application/json"},
        body: JSON.stringify({ report_key: report, question_code: QUESTION }),
        cache: "no-store",
      });
      if (!response.ok) throw new Error("UNAVAILABLE");
      const data = (await response.json()) as Answer;
      if (!verified(data, report)) throw new Error("UNQUALIFIED");
      setAnswer(data);
    } catch {
      setError("The source or model proposal did not qualify. No financial answer was released. Local budget may also be exhausted.");
    } finally {
      setBusy(false);
    }
  }
  const c = answer?.claims[0];
  return <main className={styles.page}><div className={styles.shell}>
    <header className={styles.top}><span className={styles.brand}>FR / FINANCIAL RESEARCH</span>
      <Link className={styles.back} href="/research/source-workspace">← Source workspace</Link></header>
    <section className={styles.hero}><p className={styles.kicker}>M1.7B / LOCAL DEEPSEEK EXPERIMENT</p>
      <h1>Ask the source.</h1><p>One supported question. One original disclosure. One paid model proposal, independently checked against the exact PDF cell before it appears.</p>
    </section>
    <div className={styles.grid}>
      <section className={styles.panel} aria-label="Research question">
        <p className={styles.section}>SOURCE-BOUND QUESTION</p>
        <label htmlFor="issuer" className={styles.field}>Select financial report</label>
        <select id="issuer" className={styles.select} value={report} disabled={busy}
          onChange={e => {setReport(e.target.value as Report); setAnswer(null);setError("");}}>
          <option value="600276-2026H1">恒瑞医药 (600276) · 2026 H1</option>
          <option value="600760-2026H1">中航沈飞 (600760) · 2026 H1</option>
        </select>
        <label className={styles.field}>Supported research question</label>
        <div className={styles.question}>What does the selected 2026 H1 report show in its consolidated revenue source row?</div>
        <button type="button" className={styles.button} disabled={busy} onClick={submit}>
          {busy ? "Checking source and requesting model…" : "Ask DeepSeek · one paid call"}
        </button>
        <p className={styles.note}>Clicking explicitly authorizes one paid request. No automatic retries. Maximum 4 requests per local server session. DeepSeek sees only the bounded public source packet.</p>
      </section>
      <aside className={styles.aside}><p className={styles.section}>RESEARCH BOUNDARY</p>
        <h2>Proof before prose.</h2>
        <p>The selected original PDF is hash-verified and its revenue cell is checked by an independent native-PDF location Reviewer before a model request.</p>
        <div className={styles.item}><strong>Research publication</strong> BLOCKED — always</div>
        <div className={styles.item}><strong>Financial-semantic review</strong> NOT PERFORMED</div>
        <div className={styles.item}><strong>Answer scope</strong> One verbatim consolidated revenue row; no growth, comparison, causality, valuation or trading action</div>
      </aside>
    </div>
    {error && <section className={styles.result} role="alert"><h2>Answer withheld</h2><p className={styles.warn}>{error}</p></section>}
    {answer && c && verified(answer, resultReport) && <section className={styles.result} aria-live="polite">
      <p className={styles.section}>DEEPSEEK · SOURCE-BOUND PROPOSAL</p><h2>{CATALOG[resultReport].name} · verified literal claim</h2>
      <div className={styles.claim}><p>{c.text}</p><p className={styles.muted}>Evidence ID: {c.evidence_id}</p>
        <a className={styles.source} target="_blank" rel="noopener noreferrer"
          href={`${answer.source_url}#page=${c.source_page}`}>Open original PDF · Page {c.source_page} ↗</a>
      </div>
      <p className={styles.muted}>Model: {answer.model} · Tokens: {answer.usage.total_tokens} · Estimated request cost: US${answer.usage.estimated_cost_usd_low}–${answer.usage.estimated_cost_usd_high}</p>
      <p className={styles.warn}>Literal evidence match only. Financial semantics not qualified. Research publication BLOCKED.</p>
    </section>}
    <p className={styles.note}>Financial Research Platform · Local developer experiment · No API key is sent to the browser</p>
  </div></main>;
}
