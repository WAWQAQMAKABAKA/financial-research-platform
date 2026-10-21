import Link from "next/link";
import { Suspense } from "react";
import styles from "./revenue-scope.module.css";

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

const statementInfo = [
  { number: "01", english: "Consolidated statement", description: "Source row from the consolidated income statement" },
  { number: "02", english: "Parent-company statement", description: "Source row from the parent-company income statement" },
] as const;

function UnavailableNotice() {
  return (
    <section className={styles.unavailable} role="status" aria-label="Source unavailable">
      <div className={styles.unavailableSymbol} aria-hidden="true">!</div>
      <div>
        <h2>Source draft unavailable</h2>
        <p>No financial values are shown because source identity or literal review could not be verified.</p>
        <p className={styles.muted}>Research publication remains blocked.</p>
      </div>
    </section>
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
  if (!permittedDraft(data)) return <UnavailableNotice />;

  return (
    <div className={styles.workspace}>
      <section className={styles.scopeBanner} aria-label="Interpretation boundary">
        <span className={styles.scopeIcon} aria-hidden="true">i</span>
        <div>
          <strong>Two independent source rows, not a financial comparison</strong>
          <p>These are verbatim observations from separate statements. No trend, accounting conclusion, or investment inference has been approved.</p>
        </div>
      </section>

      <div className={styles.contentGrid}>
        <section className={styles.observations} aria-labelledby="observation-title">
          <div className={styles.sectionHeading}>
            <div>
              <p className={styles.eyebrow}>EVIDENCE / ORIGINAL DISCLOSURE</p>
              <h2 id="observation-title">Reported source rows</h2>
            </div>
            <span className={styles.itemCount}>02 located cells</span>
          </div>
          <div className={styles.evidenceList}>
            {data.observations.map((o, i) => (
              <article className={styles.evidenceCard} key={o.evidence_id} aria-labelledby={`statement-${i}`}>
                <div className={styles.cardTop}>
                  <div className={styles.numberBlock} aria-hidden="true">{statementInfo[i].number}</div>
                  <div className={styles.statementHeading}>
                    <p className={styles.statementType}>{statementInfo[i].english}</p>
                    <h3 id={`statement-${i}`}>{o.statement_title.trim()}</h3>
                    <p className={styles.statementSubline}>{statementInfo[i].description}</p>
                  </div>
                  <span className={styles.citationTag}>PDF p. {o.page_number}</span>
                </div>

                <div className={styles.amountBlock}>
                  <p className={styles.amountLabel}>Reported cell value · source transcription</p>
                  <div className={styles.amountValue}>{o.value_verbatim.trim()}</div>
                  <p className={styles.amountContext}>Source-printed context: {o.statement_context}</p>
                </div>

                <div className={styles.cellFacts}>
                  <div>
                    <span>Original row label</span>
                    <strong>{o.row_label}</strong>
                  </div>
                  <div>
                    <span>Original column header</span>
                    <strong>{o.column_header}</strong>
                  </div>
                  <div>
                    <span>Table position</span>
                    <strong>Table {o.table_index} · Row {o.row_index} · Column {o.column_index}</strong>
                  </div>
                </div>

                <div className={styles.cardFooter}>
                  <div className={styles.literalReview}>
                    <span className={styles.checkMark} aria-hidden="true">✓</span>
                    <span>Literal cell/location check passed <small>· not a financial-semantic approval</small></span>
                  </div>
                  <a className={styles.sourceLink} href={`${data.source_url}#page=${o.page_number}`} target="_blank" rel="noopener noreferrer" aria-label={`Open original PDF, page ${o.page_number}, for ${o.statement_title.trim()}`}>
                    Open source · Page {o.page_number}
                    <span aria-hidden="true">↗</span>
                  </a>
                </div>
                <details className={styles.reviewDetail}>
                  <summary>See review trace</summary>
                  <p>Internal verdict: {data.reviews[i].verdict}</p>
                  <p>Scope: {o.review_scope}</p>
                  <p>Rule: {data.reviews[i].rationale}</p>
                  <p>Evidence ID: <code>{o.evidence_id}</code></p>
                </details>
              </article>
            ))}
          </div>
        </section>

        <aside className={styles.sidebar} aria-label="Source provenance and publication status">
          <section className={styles.boundaryPanel}>
            <p className={styles.eyebrow}>REVIEW BOUNDARY</p>
            <h2>Evidence is not a conclusion.</h2>
            <div className={styles.statusLine}>
              <span>Research publication</span>
              <strong>{data.research_publication}</strong>
            </div>
            <div className={styles.statusLine}>
              <span>Financial-semantic review</span>
              <strong>{data.financial_semantic_review}</strong>
            </div>
            <p className={styles.boundaryDetail}>{data.limitation}</p>
          </section>

          <section className={styles.provenancePanel}>
            <p className={styles.eyebrow}>TRACEABILITY / SOURCE IDENTITY</p>
            <h2>Document provenance</h2>
            <dl className={styles.provenanceList}>
              <div><dt>Issuer</dt><dd>恒瑞医药 · 600276</dd></div>
              <div><dt>Reporting period</dt><dd>2026 H1</dd></div>
              <div><dt>Source document</dt><dd className={styles.breakable}>{data.document_id}</dd></div>
              <div><dt>Draft generated</dt><dd className={styles.breakable}>{data.generated_at}</dd></div>
            </dl>
            <details className={styles.hashDetails}>
              <summary>View integrity hashes and draft ID</summary>
              <dl className={styles.provenanceList}>
                <div><dt>Original PDF · SHA-256</dt><dd className={styles.monospace}>{data.source_sha256}</dd></div>
                <div><dt>Canonical · SHA-256</dt><dd className={styles.monospace}>{data.canonical_sha256}</dd></div>
                <div><dt>Draft ID</dt><dd className={styles.monospace}>{data.report_id}</dd></div>
              </dl>
            </details>
            <a className={styles.provenanceLink} href={data.source_url} target="_blank" rel="noopener noreferrer">
              View original disclosure <span aria-hidden="true">↗</span>
            </a>
          </section>
        </aside>
      </div>
    </div>
  );
}

export default function RevenueScopePage() {
  return (
    <main className={styles.screen}>
      <div className={styles.container}>
        <header className={styles.siteHeader}>
          <Link href="/research" className={styles.brand} aria-label="Back to financial research home">
            <span className={styles.brandMark} aria-hidden="true">FR</span>
            <span className={styles.brandText}>FINANCIAL RESEARCH <small>Disclosure intelligence</small></span>
          </Link>
          <nav aria-label="Research navigation">
            <Link href="/research" className={styles.backLink}><span aria-hidden="true">←</span> Research home</Link>
          </nav>
        </header>

        <section className={styles.hero} aria-labelledby="page-title">
          <div className={styles.heroUpper}>
            <span className={styles.heroKicker}>FINANCIAL DISCLOSURE / SOURCE EVIDENCE</span>
            <span className={styles.previewLabel}>LOCAL RESEARCH PREVIEW</span>
          </div>
          <h1 id="page-title">恒瑞医药 <span>2026 H1 revenue evidence</span></h1>
          <p>Locate financial figures in the original filing, inspect the exact reported rows, and follow every source citation back to the disclosure.</p>
          <div className={styles.heroTags}>
            <span>600276 · SSE</span>
            <span>2026 interim report</span>
            <span>Source text only</span>
          </div>
        </section>

        <Suspense fallback={
          <section className={styles.loadingState} role="status" aria-live="polite">
            <span className={styles.loadingDot} aria-hidden="true" />
            Verifying original disclosure and source locations…
          </section>
        }>
          <LocalRevenueDraft />
        </Suspense>
        <footer className={styles.pageFooter}>
          <span>Financial Research Platform · Local development preview</span>
          <span>Source traceability first. Financial interpretation requires independent review.</span>
        </footer>
      </div>
    </main>
  );
}
