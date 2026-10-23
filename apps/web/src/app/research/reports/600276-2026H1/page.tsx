"use client";

import Link from "next/link";
import { useState } from "react";
import styles from "./report.module.css";

const REPORT_KEY = "600276-2026H1";
const QUESTION_CODE =
  "revenue_and_innovation_source_context_2026H1";

const SOURCE = {
  documentId: "600276-2026H1-cninfo-1225483600",
  url: "https://static.cninfo.com.cn/finalpage/2026-08-20/1225483600.PDF",
  sha: "ff6910663a9726acb889aa061a8bab1433f58890d81ebea013b8c637a097a7aa",
  canonicalSha:
    "96784f9deba244aab85bd117b9a1894bdcbd689a8368554f84014703f1e8b864",
} as const;

type Observation = {
  claim_id: string;
  kind: string;
  text: string;
  evidence_id: string;
  page: number;
  statement_title: string;
  row_label: string;
  column_header: string;
  value_verbatim: string;
  statement_context: string;
  review_result: string;
  review_scope: string;
};

type ManagementStatement = {
  claim_id: string;
  kind: string;
  text: string;
  evidence_id: string;
  page: number;
  review_result: string;
  review_scope: string;
};

type ReportPacket = {
  status: string;
  report_type: string;
  report_key: string;
  report_identity: string;
  source_draft_id: string;
  report_storage: string;
  question_code: string;
  question: string;
  issuer_name: string;
  report_period: string;
  as_of: string;
  generated_at: string;
  document_id: string;
  source_url: string;
  source_sha256: string;
  canonical_sha256: string;
  observations: Observation[];
  management_statement: ManagementStatement;
  analyst_interpretation: {
    status: string;
    reason: string;
  };
  financial_semantic_review: string;
  research_publication: string;
  limitations: string[];
};

const EXPECTED_ROWS = [
  { title: "合并利润表", row: "其中：营业收入" },
  { title: "母公司利润表", row: "一、营业收入" },
] as const;

const MANAGEMENT_SENTENCE =
  /^2026年上半年公司创新药销售收入\d+(?:\.\d+)?亿元，同比增长\d+(?:\.\d+)?%，占药品销售收入的比重达\d+(?:\.\d+)?%[。]$/u;

const HASH = /^[a-f0-9]{64}$/;
const AMOUNT = /^[0-9][0-9,]*\.[0-9]{2}$/;

function record(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" &&
    v !== null &&
    !Array.isArray(v);
}

function norm(v: string): string {
  return v.replace(/\s/g, "");
}

function verifiedReport(v: unknown): v is ReportPacket {
  if (!record(v)) return false;

  const r = v;
  const management = r.management_statement;
  const interpretation = r.analyst_interpretation;

  if (
    r.status !== "LOCAL_SOURCE_REPORT_READY" ||
    r.report_type !== "UNPUBLISHED_SOURCE_REPORT_PREVIEW" ||
    r.report_key !== REPORT_KEY ||
    r.question_code !== QUESTION_CODE ||
    r.issuer_name !== "恒瑞医药" ||
    r.report_period !== "2026H1" ||
    r.document_id !== SOURCE.documentId ||
    r.source_url !== SOURCE.url ||
    r.source_sha256 !== SOURCE.sha ||
    r.canonical_sha256 !== SOURCE.canonicalSha ||
    r.report_storage !== "NOT_PERSISTED" ||
    r.research_publication !== "BLOCKED" ||
    r.financial_semantic_review !== "NOT_PERFORMED" ||
    typeof r.report_identity !== "string" ||
    !HASH.test(r.report_identity) ||
    typeof r.source_draft_id !== "string" ||
    !HASH.test(r.source_draft_id) ||
    typeof r.as_of !== "string" ||
    !Number.isFinite(Date.parse(r.as_of)) ||
    typeof r.generated_at !== "string" ||
    !Number.isFinite(Date.parse(r.generated_at)) ||
    typeof r.question !== "string" ||
    !r.question.trim() ||
    !Array.isArray(r.observations) ||
    r.observations.length !== 2 ||
    !record(management) ||
    !record(interpretation) ||
    interpretation.status !== "WITHHELD" ||
    interpretation.reason !==
      "FINANCIAL_SEMANTIC_REVIEW_NOT_PERFORMED" ||
    !Array.isArray(r.limitations) ||
    r.limitations.length !== 3 ||
    !r.limitations.every(
      (x: unknown) => typeof x === "string" && !!x.trim()
    )
  ) {
    return false;
  }

  const evidenceIds = new Set<string>();

  for (let i = 0; i < 2; i++) {
    const o = r.observations[i];
    const expected = EXPECTED_ROWS[i];

    if (!record(o)) return false;

    if (
      o.claim_id !== `REV${i + 1}` ||
      o.kind !== "SOURCE_LITERAL_OBSERVATION" ||
      typeof o.statement_title !== "string" ||
      norm(o.statement_title) !== expected.title ||
      typeof o.row_label !== "string" ||
      norm(o.row_label) !== expected.row ||
      typeof o.column_header !== "string" ||
      norm(o.column_header) !== "2026年半年度" ||
      typeof o.value_verbatim !== "string" ||
      !AMOUNT.test(o.value_verbatim) ||
      typeof o.statement_context !== "string" ||
      !o.statement_context.trim() ||
      typeof o.evidence_id !== "string" ||
      !HASH.test(o.evidence_id) ||
      typeof o.page !== "number" ||
      !Number.isInteger(o.page) ||
      o.page < 1 ||
      o.page > 182 ||
      o.review_result !== "SOURCE_LOCATION_VERIFIED_ONLY" ||
      o.review_scope !== "LITERAL_CELL_LOCATION_ONLY" ||
      typeof o.text !== "string" ||
      o.text !==
        `In the source section "${o.statement_title}", ` +
        `the row "${o.row_label}" under ` +
        `"${o.column_header}" reads "${o.value_verbatim}".` ||
      evidenceIds.has(o.evidence_id)
    ) {
      return false;
    }

    evidenceIds.add(o.evidence_id);
  }

  return (
    management.claim_id === "M1" &&
    management.kind === "ATTRIBUTED_MANAGEMENT_STATEMENT" &&
    management.review_result === "SOURCE_PASSAGE_LOCATED_ONLY" &&
    management.review_scope ===
      "NATIVE_PDF_TEXT_AND_WORD_LOCATION_ONLY" &&
    management.page === 20 &&
    typeof management.text === "string" &&
    MANAGEMENT_SENTENCE.test(management.text) &&
    typeof management.evidence_id === "string" &&
    HASH.test(management.evidence_id) &&
    !evidenceIds.has(management.evidence_id)
  );
}

function OriginalLink({ page }: { page: number }) {
  return (
    <a
      className={styles.source}
      href={`${SOURCE.url}#page=${page}`}
      target="_blank"
      rel="noopener noreferrer"
    >
      Open original disclosure · PDF p. {page} ↗
    </a>
  );
}

export default function HengruiSourceReport() {
  const [report, setReport] = useState<ReportPacket | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function loadReport() {
    if (loading) return;

    setLoading(true);
    setReport(null);
    setError("");

    try {
      const response = await fetch("/api/local-source-report", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ report_key: REPORT_KEY }),
        cache: "no-store",
      });

      if (!response.ok) throw new Error("REPORT_UNAVAILABLE");

      const packet: unknown = await response.json();

      if (!verifiedReport(packet)) {
        throw new Error("REPORT_CONTRACT_NOT_QUALIFIED");
      }

      setReport(packet);
    } catch {
      setError(
        "The verified report is unavailable or did not meet its " +
        "source/review contract. No report content was released."
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className={styles.page}>
      <div className={styles.shell}>
        <header className={styles.top}>
          <Link href="/research" className={styles.brand}>
            FR / FINANCIAL RESEARCH
          </Link>
          <Link href="/research/source-workspace"
            className={styles.back}>
            Source workspace ↗
          </Link>
        </header>

        <section className={styles.hero}>
          <p className={styles.kicker}>
            M112 / SOURCE-BOUND RESEARCH REPORT
          </p>
          <h1>
            恒瑞医药 <span>2026 H1 Research</span>
          </h1>
          <p>
            A readable, traceable account of two income-statement
            source observations and an attributed management
            discussion. No valuation, accounting reconciliation,
            investment conclusion or recommendation.
          </p>
          <div className={styles.heroMeta}>
            <span>600276 · 2026 H1</span>
            <span>Original disclosure · 20 Aug 2026</span>
            <span>LOCAL / UNPUBLISHED</span>
          </div>
        </section>

        <div className={styles.toolbar}>
          <div>
            <strong>Assemble original-source report</strong>
            <p>
              Rechecks the local hash-pinned PDF.
              No paid model call, persistence or publication.
            </p>
          </div>
          <button
            type="button"
            className={styles.button}
            onClick={loadReport}
            disabled={loading}
          >
            {loading
              ? "Verifying original disclosure…"
              : "Generate report preview"}
          </button>
        </div>

        {error && (
          <div className={styles.error} role="alert">
            <strong>Report withheld</strong>
            <p>{error}</p>
            <p>Financial-semantic approval and publication remain blocked.</p>
          </div>
        )}

        {!report && !error && (
          <section className={styles.empty} aria-live="polite">
            <h2>{loading ? "Checking evidence…" : "Report not yet assembled"}</h2>
            <p>
              Report content is displayed only after the original
              disclosure and source bindings pass verification.
            </p>
          </section>
        )}

        {report && (
          <div aria-live="polite">
            <section
              className={styles.answerFirst}
              aria-label="Source-bound research answer"
            >
              <p className={styles.kicker}>
                SOURCE-BOUND ANSWER / READ FIRST
              </p>
              <h2>What the located evidence shows</h2>
              <p className={styles.answerIntro}>
                Two separately identified financial-statement rows
                and one attributed management passage were located
                in the original Hengrui disclosure. The values below
                retain their original source context.
              </p>

              <div className={styles.answerGrid}>
                {report.observations.map((o) => (
                  <article
                    className={styles.answerItem}
                    key={o.claim_id}
                  >
                    <span className={styles.smallTag}>
                      {o.claim_id} · SOURCE CELL
                    </span>
                    <h3>{o.statement_title}</h3>
                    <p className={styles.answerRow}>
                      {o.row_label}
                    </p>
                    <p className={styles.answerValue}>
                      {o.value_verbatim}
                    </p>
                    <p className={styles.answerContext}>
                      Original source context: {o.statement_context}
                    </p>
                    <OriginalLink page={o.page} />
                  </article>
                ))}
              </div>

              <article className={styles.answerManagement}>
                <span className={styles.smallTag}>
                  M1 · ATTRIBUTED MANAGEMENT DISCLOSURE
                </span>
                <h3>Innovative-drug sales discussion</h3>
                <blockquote className={styles.answerPassage}>
                  {report.management_statement.text}
                </blockquote>
                <p className={styles.answerContext}>
                  This is management&apos;s disclosed wording, not an
                  independently approved financial interpretation.
                </p>
                <OriginalLink
                  page={report.management_statement.page}
                />
              </article>

              <div className={styles.answerBoundary}>
                <strong>
                  What these three evidence items do not establish
                </strong>
                <p>
                  This assembled evidence packet does not establish
                  accounting comparability between the two statement
                  rows, a reconciliation with the management sales
                  figure, a causal explanation, or company-wide
                  performance growth. It does not imply that the
                  complete disclosure lacks other relevant evidence.
                </p>
                <p>
                  Analyst interpretation: WITHHELD.
                  Financial-semantic review: NOT PERFORMED.
                  Publication: BLOCKED.
                </p>
              </div>
            </section>

            <div className={styles.summary}>
              <div>
                <span>Financial statement observations</span>
                <strong>02</strong>
                <small>Literal source text/location checked</small>
              </div>
              <div>
                <span>Management disclosures</span>
                <strong>01</strong>
                <small>Attributed original passage</small>
              </div>
              <div>
                <span>Financial-semantic qualification</span>
                <strong className={styles.blocked}>NOT PERFORMED</strong>
                <small>Publication BLOCKED</small>
              </div>
            </div>

            <section className={styles.intro}>
              <p className={styles.kicker}>01 / RESEARCH QUESTION</p>
              <h2>Revenue source and management context</h2>
              <p>{report.question}</p>
              <p className={styles.note}>
                This preview reports only what was independently
                located in the disclosure. The observations below
                have not been qualified for financial comparability.
              </p>
            </section>

            <div className={styles.grid}>
              <div>
                <section className={styles.sectionBlock}>
                  <div className={styles.sectionHead}>
                    <div>
                      <p className={styles.kicker}>02 / SOURCE OBSERVATIONS</p>
                      <h2>Financial statement evidence</h2>
                    </div>
                    <span className={styles.smallTag}>2 verified locations</span>
                  </div>

                  {report.observations.map((o, i) => (
                    <article className={styles.card} key={o.claim_id}>
                      <div className={styles.cardTop}>
                        <span className={styles.smallTag}>
                          {o.claim_id} · ORIGINAL SOURCE CELL
                        </span>
                        <span>0{i + 1}</span>
                      </div>
                      <h3>{o.statement_title}</h3>
                      <div className={styles.value}>{o.value_verbatim}</div>
                      <p className={styles.label}>
                        Original row: {o.row_label}
                      </p>
                      <p className={styles.label}>
                        Column: {o.column_header}
                      </p>
                      <p className={styles.note}>
                        Printed context: {o.statement_context}
                      </p>
                      <div className={styles.review}>
                        {o.review_result.replaceAll("_", " ")}
                        <p>
                          This check establishes literal source
                          location, not accounting meaning.
                        </p>
                      </div>
                      <OriginalLink page={o.page} />
                      <details className={styles.details}>
                        <summary>Claim and evidence trace</summary>
                        <p>{o.text}</p>
                        <p>Review scope: {o.review_scope}</p>
                        <p className={styles.hash}>
                          Evidence ID: {o.evidence_id}
                        </p>
                      </details>
                    </article>
                  ))}
                </section>

                <section className={styles.sectionBlock}>
                  <p className={styles.kicker}>03 / MANAGEMENT DISCUSSION</p>
                  <h2>What management disclosed</h2>
                  <article className={styles.card}>
                    <span className={styles.smallTag}>
                      M1 · ATTRIBUTED MANAGEMENT STATEMENT
                    </span>
                    <blockquote className={styles.passage}>
                      {report.management_statement.text}
                    </blockquote>
                    <p className={styles.note}>
                      The percentages and denominator above are
                      management&apos;s wording in the original disclosure.
                      This is not an independently established
                      accounting relationship.
                    </p>
                    <div className={styles.review}>
                      SOURCE PASSAGE LOCATED ONLY
                    </div>
                    <OriginalLink
                      page={report.management_statement.page}
                    />
                    <details className={styles.details}>
                      <summary>Evidence and review trace</summary>
                      <p>
                        Review scope:{" "}
                        {report.management_statement.review_scope}
                      </p>
                      <p className={styles.hash}>
                        Evidence ID:{" "}
                        {report.management_statement.evidence_id}
                      </p>
                    </details>
                  </article>
                </section>

                <section className={styles.sectionBlock}>
                  <p className={styles.kicker}>04 / ANALYST INTERPRETATION</p>
                  <h2>Interpretation withheld</h2>
                  <div className={styles.withheld}>
                    <strong>{report.analyst_interpretation.status}</strong>
                    <p>
                      {report.analyst_interpretation.reason.replaceAll(
                        "_", " "
                      )}
                    </p>
                    <p>
                      No financial reconciliation, causal explanation,
                      investment thesis or forward-looking conclusion
                      is authorized by this source-only report.
                    </p>
                  </div>
                </section>
              </div>

              <aside className={styles.side}>
                <section className={styles.sideCard}>
                  <p className={styles.kicker}>PUBLICATION BOUNDARY</p>
                  <h2>Evidence, not approval</h2>
                  <dl className={styles.facts}>
                    <div>
                      <dt>Research publication</dt>
                      <dd>{report.research_publication}</dd>
                    </div>
                    <div>
                      <dt>Financial semantics</dt>
                      <dd>{report.financial_semantic_review}</dd>
                    </div>
                    <div>
                      <dt>Storage</dt>
                      <dd>{report.report_storage}</dd>
                    </div>
                  </dl>
                </section>

                <section className={styles.sideCard}>
                  <p className={styles.kicker}>SOURCE PROVENANCE</p>
                  <h2>Original disclosure</h2>
                  <p className={styles.note}>
                    恒瑞医药 · 2026 H1
                  </p>
                  <a
                    className={styles.source}
                    href={SOURCE.url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Open full original PDF ↗
                  </a>
                  <details className={styles.details}>
                    <summary>Report identity and hashes</summary>
                    <p className={styles.hash}>
                      Report identity: {report.report_identity}
                    </p>
                    <p className={styles.hash}>
                      Source draft ID: {report.source_draft_id}
                    </p>
                    <p className={styles.hash}>
                      Document: {report.document_id}
                    </p>
                    <p className={styles.hash}>
                      Original SHA-256: {report.source_sha256}
                    </p>
                    <p className={styles.hash}>
                      Canonical SHA-256:{" "}
                      {report.canonical_sha256}
                    </p>
                    <p className={styles.hash}>
                      As-of: {report.as_of}
                    </p>
                    <p className={styles.hash}>
                      Generated: {report.generated_at}
                    </p>
                  </details>
                </section>

                <section className={styles.sideCard}>
                  <p className={styles.kicker}>RESEARCH LIMITATIONS</p>
                  <ul className={styles.limits}>
                    {report.limitations.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </section>
              </aside>
            </div>
          </div>
        )}

        <footer className={styles.footer}>
          <span>Financial Research Platform · Source report preview</span>
          <span>No customer publication or financial-semantic approval</span>
        </footer>
      </div>
    </main>
  );
}
