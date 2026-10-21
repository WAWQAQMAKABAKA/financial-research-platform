import Link from "next/link";
import { Suspense } from "react";

// Source-only local preview. Nothing in this page authorizes financial publication.
const DOCUMENT_ID = "600276-2026H1-cninfo-1225483600";
const PDF_URL = "https://static.cninfo.com.cn/finalpage/2026-08-20/1225483600.PDF";
const PDF_SHA = "ff6910663a9726acb889aa061a8bab1433f58890d81ebea013b8c637a097a7aa";
const CANONICAL_SHA = "96784f9deba244aab85bd117b9a1894bdcbd689a8368554f84014703f1e8b864";

type Observation = {
  claim_id: string;
  evidence_id: string;
  statement_title: string;
  statement_type_candidate: string;
  row_label: string;
  column_header: string;
  value_verbatim: string;
  statement_context: string;
  page_number: number;
  table_index: number;
  row_index: number;
  column_index: number;
  cell_bbox_pt: number[];
  source_text_span_status: string;
  review_scope: string;
};
type Claim = { claim_id: string; text: string; evidence_ids: string[] };
type Review = { claim_id: string; verdict: string; rationale: string };
type Draft = {
  status: string;
  question?: string;
  report_id?: string;
  document_id?: string;
  source_url?: string;
  source_sha256?: string;
  canonical_sha256?: string;
  generated_at?: string;
  financial_semantic_review?: string;
  research_publication: string;
  limitation?: string;
  observations: Observation[];
  claims: Claim[];
  reviews: Review[];
};

function permittedDraft(d: Draft | null): d is Draft {
  if (!d || d.status !== "SOURCE_DRAFT_READY" ||
      d.document_id !== DOCUMENT_ID || d.source_url !== PDF_URL ||
      d.research_publication !== "BLOCKED" ||
      d.financial_semantic_review !== "NOT_PERFORMED" ||
      !Array.isArray(d.claims) || !Array.isArray(d.reviews) ||
      !Array.isArray(d.observations) || d.claims.length !== 2 ||
      d.reviews.length !== 2 || d.observations.length !== 2 ||
      d.source_sha256 !== PDF_SHA ||
      d.canonical_sha256 !== CANONICAL_SHA ||
      !d.report_id?.match(/^[a-f0-9]{64}$/)) return false;
  const kinds = ["consolidated_income_statement", "parent_income_statement"];
  return d.observations.every((o, i) =>
    o.statement_type_candidate === kinds[i] &&
    o.statement_title.trim() === (i === 0 ? "合并利润表" : "母公司利润表") &&
    o.column_header.replace(/\s/g, "") === "2026年半年度" &&
    /^[0-9,]+\.[0-9]{2}$/.test(o.value_verbatim.trim()) &&
    Number.isInteger(o.page_number) && o.page_number > 0 &&
    o.source_text_span_status === "NOT_PROVEN_FROM_TABLE_GEOMETRY" &&
    o.review_scope === "LITERAL_CELL_LOCATION_ONLY" &&
    Array.isArray(o.cell_bbox_pt) && o.cell_bbox_pt.length === 4 &&
    o.cell_bbox_pt.every(Number.isFinite) &&
    d.claims[i].claim_id === o.claim_id &&
    d.claims[i].evidence_ids.length === 1 &&
    d.claims[i].evidence_ids[0] === o.evidence_id &&
    d.reviews[i].claim_id === o.claim_id &&
    d.reviews[i].verdict === "ADMIT"
  );
}

async function LocalRevenueDraft() {
  let data: Draft | null = null;
  try {
    const base = process.env.RESEARCH_API_BASE_URL ?? "http://127.0.0.1:8000";
    const response = await fetch(`${base}/api/v1/research/revenue-scope-preview`, {
      cache: "no-store",
    });
    if (response.ok) data = (await response.json()) as Draft;
  } catch {
    data = null;
  }
  if (!permittedDraft(data)) {
    return <p role="status">Source draft: UNAVAILABLE — no unverified numbers displayed.</p>;
  }
  return (
    <section style={{ marginTop: 26 }} aria-label="Hengrui source draft">
      <h2>Reported source rows</h2>
      <p><strong>Local source-only draft · NOT a reviewed financial conclusion</strong></p>
      <p>These are two separately labeled source rows, not a revenue comparison or investment conclusion.</p>
      <div style={{ display: "grid", gap: 18, marginTop: 18 }}>
        {data.observations.map((o, i) => (
          <article key={o.evidence_id} style={{ border: "1px solid #888", borderRadius: 10, padding: 18 }}>
            <h3>{o.statement_title}</h3>
            <p style={{ fontSize: 26, fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{o.value_verbatim.trim()}</p>
            <p>Source row: {o.row_label} · Source column: {o.column_header}</p>
            <p>Original statement context: {o.statement_context}</p>
            <p>Claim-level literal review: {data.reviews[i].verdict} — {data.reviews[i].rationale}</p>
            <p>Source location: PDF page {o.page_number}, table {o.table_index}, row {o.row_index}, column {o.column_index}</p>
            <p><a style={{ textDecoration: "underline" }} href={`${PDF_URL}#page=${o.page_number}`} target="_blank" rel="noopener noreferrer">Open original CNINFO report — PDF page {o.page_number}</a></p>
          </article>
        ))}
      </div>
      <h2 style={{ marginTop: 26 }}>Source identity and review boundary</h2>
      <p>Document: {data.document_id}</p>
      <p style={{ overflowWrap: "anywhere" }}>Draft ID: {data.report_id}</p>
      <p style={{ overflowWrap: "anywhere" }}>Source SHA-256: {data.source_sha256}</p>
      <p style={{ overflowWrap: "anywhere" }}>Canonical SHA-256: {data.canonical_sha256}</p>
      <p>Generated: {data.generated_at}</p>
      <p><strong>Research publication: BLOCKED. Financial-semantic review: NOT PERFORMED.</strong></p>
      <p>{data.limitation}</p>
    </section>
  );
}

export default function RevenueScopePage() {
  return (
    <main style={{ maxWidth: 900, margin: "45px auto", padding: 24, fontFamily: "Arial, sans-serif" }}>
      <Link href="/research">Back to research</Link>
      <h1>恒瑞医药 · 2026 H1 revenue source evidence</h1>
      <p>Two source-scoped financial cells, with original PDF citations and literal claim review.</p>
      <Suspense fallback={<p>Verifying original source and document locations...</p>}>
        <LocalRevenueDraft />
      </Suspense>
    </main>
  );
}
