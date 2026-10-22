import Link from "next/link";
import { Suspense } from "react";
import styles from "../revenue-scope/revenue-scope.module.css";

// Trusted local demo catalog: metadata only, no expected financial answers.
const REPORTS = {
  "600276-2026H1": {
    name: "恒瑞医药", ticker: "600276", period: "2026 H1",
    documentId: "600276-2026H1-cninfo-1225483600",
    sourceUrl: "https://static.cninfo.com.cn/finalpage/2026-08-20/1225483600.PDF",
    sourceSha: "ff6910663a9726acb889aa061a8bab1433f58890d81ebea013b8c637a097a7aa",
    canonicalSha: "96784f9deba244aab85bd117b9a1894bdcbd689a8368554f84014703f1e8b864",
  },
  "600760-2026H1": {
    name: "中航沈飞", ticker: "600760", period: "2026 H1",
    documentId: "600760-2026H1-cninfo-1225517994",
    sourceUrl: "https://static.cninfo.com.cn/finalpage/2026-08-28/1225517994.PDF",
    sourceSha: "d53ee98c091fdcbb8df3ebcc3f8d9bef87f61b374615dc3165dadb594f637d99",
    canonicalSha: "620d3a30f73423527dd662e21ebf3367b546dfa6795c6fcf618f35ebf0008aa5",
  },
} as const;
type ReportKey = keyof typeof REPORTS;

type Observation = {
  claim_id: string; evidence_id: string;
  statement_type_candidate: string; statement_title: string;
  row_label: string; column_header: string; value_verbatim: string;
  statement_context: string; page_number: number; table_index: number;
  row_index: number; column_index: number; cell_bbox_pt: number[];
  source_text_span_status: string; review_scope: string;
};
type Draft = {
  status: string; report_key?: string; report_id?: string;
  issuer_name?: string; document_id?: string; ticker?: string;
  report_period?: string; source_url?: string; source_sha256?: string;
  canonical_sha256?: string; research_publication: string;
  financial_semantic_review?: string; limitation?: string;
  observations: Observation[];
  claims: Array<{ claim_id: string; kind: string; evidence_ids: string[] }>;
  reviews: Array<{ claim_id: string; verdict: string; rationale: string }>;
};

function allowed(data: Draft | null, report: ReportKey): data is Draft {
  if (!data || data.status !== "SOURCE_DRAFT_READY" ||
      data.report_key !== report ||
      data.document_id !== REPORTS[report].documentId ||
      data.ticker !== REPORTS[report].ticker ||
      data.issuer_name !== REPORTS[report].name ||
      data.report_period !== "2026H1" ||
      data.source_url !== REPORTS[report].sourceUrl ||
      data.source_sha256 !== REPORTS[report].sourceSha ||
      data.canonical_sha256 !== REPORTS[report].canonicalSha ||
      !/^[0-9a-f]{64}$/.test(data.report_id ?? "") ||
      data.research_publication !== "BLOCKED" ||
      data.financial_semantic_review !== "NOT_PERFORMED" ||
      !Array.isArray(data.observations) || data.observations.length !== 1 ||
      !Array.isArray(data.claims) || data.claims.length !== 1 ||
      !Array.isArray(data.reviews) || data.reviews.length !== 1) return false;
  const o = data.observations[0];
  const c = data.claims[0];
  const r = data.reviews[0];
  return o.statement_type_candidate === "consolidated_income_statement" &&
    o.statement_title.trim() === "合并利润表" &&
    o.row_label.replace(/\s/g, "") === "其中：营业收入" &&
    o.column_header.replace(/\s/g, "") === "2026年半年度" &&
    /^[0-9,]+\.[0-9]{2}$/.test(o.value_verbatim.trim()) &&
    Number.isInteger(o.page_number) && o.page_number > 0 &&
    Array.isArray(o.cell_bbox_pt) && o.cell_bbox_pt.length === 4 &&
    o.cell_bbox_pt.every(Number.isFinite) &&
    o.source_text_span_status === "NOT_PROVEN_FROM_TABLE_GEOMETRY" &&
    o.review_scope === "LITERAL_CELL_LOCATION_ONLY" &&
    c.kind === "OBSERVED_FACT" &&
    c.claim_id === o.claim_id &&
    Array.isArray(c.evidence_ids) && c.evidence_ids.length === 1 &&
    c.evidence_ids[0] === o.evidence_id &&
    r.claim_id === o.claim_id &&
    r.verdict === "ADMIT" &&
    r.rationale === "LITERAL_CELL_AND_HEADING_SOURCE_CHECK_ONLY";
}

function Unavailable() {
  return (
    <section className={styles.unavailable} role="status">
      <div className={styles.unavailableSymbol} aria-hidden="true">!</div>
      <div>
        <h2>Source observation unavailable</h2>
        <p>The selected report, original PDF, cell location or literal reviewer did not qualify.</p>
        <p className={styles.muted}>No unverified financial values shown. Research publication remains blocked.</p>
      </div>
    </section>
  );
}

async function SourceResult({ report }: { report: ReportKey }) {
  let data: Draft | null = null;
  try {
    const base = process.env.RESEARCH_API_BASE_URL ?? "http://127.0.0.1:8000";
    const response = await fetch(`${base}/api/v1/research/source-workspace/${report}`, {
      cache: "no-store",
    });
    if (response.ok) data = (await response.json()) as Draft;
  } catch {
    data = null;
  }
  if (!allowed(data, report)) return <Unavailable />;
  const o = data.observations[0];
  return (
    <div className={styles.workspace}>
      <section className={styles.scopeBanner} aria-label="Interpretation boundary">
        <span className={styles.scopeIcon} aria-hidden="true">i</span>
        <div>
          <strong>One source row from one selected disclosure — not a comparison</strong>
          <p>The figure below is literal source evidence. No cross-issuer analysis, financial interpretation or investment conclusion is approved.</p>
        </div>
      </section>
      <div className={styles.contentGrid}>
        <section className={styles.observations} aria-label="Selected source evidence">
          <div className={styles.sectionHeading}>
            <div><p className={styles.eyebrow}>EVIDENCE / ORIGINAL DISCLOSURE</p><h2>Reported source row</h2></div>
            <span className={styles.itemCount}>01 located cell</span>
          </div>
          <article className={styles.evidenceCard}>
            <div className={styles.cardTop}>
              <div className={styles.numberBlock} aria-hidden="true">01</div>
              <div className={styles.statementHeading}>
                <p className={styles.statementType}>Consolidated income statement · Source candidate</p>
                <h3>{o.statement_title.trim()}</h3>
                <p className={styles.statementSubline}>Issuer: {data.issuer_name} · {data.ticker}</p>
              </div>
              <span className={styles.citationTag}>PDF p. {o.page_number}</span>
            </div>
            <div className={styles.amountBlock}>
              <p className={styles.amountLabel}>Reported cell value · original transcription</p>
              <div className={styles.amountValue}>{o.value_verbatim.trim()}</div>
              <p className={styles.amountContext}>Source-printed context: {o.statement_context}</p>
            </div>
            <div className={styles.cellFacts}>
              <div><span>Original row label</span><strong>{o.row_label}</strong></div>
              <div><span>Original column header</span><strong>{o.column_header}</strong></div>
              <div><span>Table position</span><strong>Table {o.table_index} · Row {o.row_index} · Column {o.column_index}</strong></div>
            </div>
            <div className={styles.cardFooter}>
              <div className={styles.literalReview}><span className={styles.checkMark} aria-hidden="true">✓</span>
                <span>Source text checked <small>· not an accounting qualification</small></span></div>
              <a className={styles.sourceLink} href={`${data.source_url}#page=${o.page_number}`}
                target="_blank" rel="noopener noreferrer">
                Open original · Page {o.page_number} <span aria-hidden="true">↗</span>
              </a>
            </div>
            <details className={styles.reviewDetail}>
              <summary>Review trace</summary>
              <p>Literal verdict: {data.reviews[0].verdict} · {data.reviews[0].rationale}</p>
              <p>Scope: {o.review_scope}</p>
              <p>Evidence ID: <code>{o.evidence_id}</code></p>
            </details>
          </article>
        </section>
        <aside className={styles.sidebar} aria-label="Source provenance and limitations">
          <section className={styles.boundaryPanel}>
            <p className={styles.eyebrow}>REVIEW BOUNDARY</p>
            <h2>Evidence is not a conclusion.</h2>
            <div className={styles.statusLine}><span>Publication</span><strong>{data.research_publication}</strong></div>
            <div className={styles.statusLine}><span>Financial-semantic review</span><strong>{data.financial_semantic_review}</strong></div>
            <p className={styles.boundaryDetail}>{data.limitation}</p>
          </section>
          <section className={styles.provenancePanel}>
            <p className={styles.eyebrow}>TRACEABILITY / SOURCE IDENTITY</p>
            <h2>Document provenance</h2>
            <dl className={styles.provenanceList}>
              <div><dt>Issuer</dt><dd>{data.issuer_name} · {data.ticker}</dd></div>
              <div><dt>Reporting period</dt><dd>{REPORTS[report].period}</dd></div>
              <div><dt>Source document</dt><dd className={styles.breakable}>{data.document_id}</dd></div>
            </dl>
            <details className={styles.hashDetails}>
              <summary>Integrity hashes and draft identity</summary>
              <dl className={styles.provenanceList}>
                <div><dt>Original PDF SHA-256</dt><dd className={styles.monospace}>{data.source_sha256}</dd></div>
                <div><dt>Canonical SHA-256</dt><dd className={styles.monospace}>{data.canonical_sha256}</dd></div>
                <div><dt>Draft ID</dt><dd className={styles.monospace}>{data.report_id}</dd></div>
              </dl>
            </details>
            <a className={styles.provenanceLink} href={data.source_url} target="_blank" rel="noopener noreferrer">
              Open original CNINFO disclosure <span aria-hidden="true">↗</span>
            </a>
          </section>
        </aside>
      </div>
    </div>
  );
}

async function WorkspaceContent({ searchParams }: {
  searchParams: Promise<{ report?: string | string[] }>;
}) {
  const q = await searchParams;
  const requested = typeof q.report === "string" ? q.report : "600276-2026H1";
  if (!Object.prototype.hasOwnProperty.call(REPORTS, requested)) return <Unavailable />;
  return <SourceResult report={requested as ReportKey} />;
}

export default function SourceWorkspacePage({ searchParams }: {
  searchParams: Promise<{ report?: string | string[] }>;
}) {
  return (
    <main className={styles.screen}>
      <div className={styles.container}>
        <header className={styles.siteHeader}>
          <Link href="/research" className={styles.brand}>
            <span className={styles.brandMark} aria-hidden="true">FR</span>
            <span className={styles.brandText}>FINANCIAL RESEARCH <small>Disclosure intelligence</small></span>
          </Link>
          <nav><Link className={styles.backLink} href="/research">← Research home</Link></nav>
        </header>
        <section className={styles.hero}>
          <div className={styles.heroUpper}>
            <span className={styles.heroKicker}>FINANCIAL DISCLOSURE / SOURCE WORKSPACE</span>
            <span className={styles.previewLabel}>LOCAL / TWO REPORTS</span>
          </div>
          <h1>Explore a source <span>2026 H1 financial evidence</span></h1>
          <p>Select a report. Both disclosures pass through the same source-indexing and literal-review workflow. This is not a cross-company comparison.</p>
          <div className={styles.heroTags} aria-label="Select research report">
            {Object.entries(REPORTS).map(([key, info]) => (
              <Link key={key} href={`/research/source-workspace?report=${key}`}
                style={{ color: "#f1fbfb", fontSize: 13, border: "1px solid #9dbec1", padding: "10px 15px", borderRadius: 8 }}>
                {info.name} · {info.ticker}
              </Link>
            ))}
          </div>
        </section>
        <Suspense fallback={<section className={styles.loadingState} role="status">Verifying selected original report…</section>}>
          <WorkspaceContent searchParams={searchParams} />
        </Suspense>
        <footer className={styles.pageFooter}>
          <span>Two-issuer source-only development workspace</span>
          <span>Financial-semantic approval and publication are not available.</span>
        </footer>
      </div>
    </main>
  );
}
