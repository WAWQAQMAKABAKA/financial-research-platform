"use client";

import Link from "next/link";
import { useState } from "react";
import styles from "../../ask/ask.module.css";

const REPORT_KEY = "600276-2026H1";

const SOURCE = {
  documentId: "600276-2026H1-cninfo-1225483600",
  url: "https://static.cninfo.com.cn/finalpage/2026-08-20/1225483600.PDF",
  sha: "ff6910663a9726acb889aa061a8bab1433f58890d81ebea013b8c637a097a7aa",
  canonicalSha:
    "96784f9deba244aab85bd117b9a1894bdcbd689a8368554f84014703f1e8b864",
} as const;

type ReviewPacket = {
  status: string;
  report_key: string;
  review_id: string;
  as_of: string;
  draft_origin: string;
  document_id: string;
  source_url: string;
  source_sha256: string;
  canonical_sha256: string;
  research_publication: string;
  financial_semantic_review: string;
  claim: {
    claim_id: string;
    kind: string;
    text: string;
    evidence_ids: string[];
  };
  review: {
    claim_id: string;
    verdict: string;
    reason: string;
    compared_evidence_ids: string[];
    review_scope: string;
  };
  evidence: {
    evidence_id: string;
    source_page: number;
    excerpt: string;
    review_scope: string;
  };
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" &&
    value !== null &&
    !Array.isArray(value);
}

function validPacket(
  value: unknown,
  submittedText: string,
): value is ReviewPacket {
  if (!isRecord(value)) return false;

  const a = value;
  const c = a.claim;
  const r = a.review;
  const e = a.evidence;

  if (!isRecord(c) || !isRecord(r) || !isRecord(e)) {
    return false;
  }

  if (
    a.status !== "UNPUBLISHED_ANALYST_CANDIDATE_REVIEWED" ||
    a.report_key !== REPORT_KEY ||
    a.draft_origin !== "MANUAL_ANALYST_DRAFT" ||
    a.document_id !== SOURCE.documentId ||
    a.source_url !== SOURCE.url ||
    a.source_sha256 !== SOURCE.sha ||
    a.canonical_sha256 !== SOURCE.canonicalSha ||
    a.research_publication !== "BLOCKED" ||
    a.financial_semantic_review !== "NOT_QUALIFIED" ||
    c.claim_id !== "MC1" ||
    c.kind !== "OBSERVED_FACT" ||
    c.text !== submittedText ||
    r.claim_id !== c.claim_id ||
    r.review_scope !== "BOUNDED_NARRATIVE_CONTRADICTION_ONLY" ||
    e.review_scope !== "NATIVE_PDF_TEXT_AND_WORD_LOCATION_ONLY" ||
    e.source_page !== 20
  ) {
    return false;
  }

  const hash = /^[0-9a-f]{64}$/;

  if (
    typeof a.review_id !== "string" ||
    !hash.test(a.review_id) ||
    typeof a.as_of !== "string" ||
    !Number.isFinite(Date.parse(a.as_of)) ||
    typeof e.evidence_id !== "string" ||
    !hash.test(e.evidence_id) ||
    typeof e.excerpt !== "string" ||
    !e.excerpt.trim() ||
    typeof r.reason !== "string" ||
    !r.reason.trim() ||
    !["REJECT", "UNCERTAIN"].includes(String(r.verdict)) ||
    !Array.isArray(c.evidence_ids) ||
    !Array.isArray(r.compared_evidence_ids)
  ) {
    return false;
  }

  return (
    c.evidence_ids.length === 1 &&
    r.compared_evidence_ids.length === 1 &&
    c.evidence_ids[0] === e.evidence_id &&
    r.compared_evidence_ids[0] === e.evidence_id
  );
}

export default function ManualAnalystReviewPage() {
  const [draft, setDraft] = useState("");
  const [result, setResult] = useState<ReviewPacket | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function reviewDraft() {
    if (busy || !draft.trim()) return;

    const submittedText = draft;
    setBusy(true);
    setResult(null);
    setError("");

    try {
      const response = await fetch(
        "/api/local-analyst-draft-review",
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            report_key: REPORT_KEY,
            candidate_text: submittedText,
          }),
          cache: "no-store",
        },
      );

      if (!response.ok) {
        throw new Error("REVIEW_UNAVAILABLE");
      }

      const packet: unknown = await response.json();

      if (!validPacket(packet, submittedText)) {
        throw new Error("REVIEW_CONTRACT_FAILED");
      }

      setResult(packet);
    } catch {
      setError(
        "Review unavailable or source verification failed. " +
        "No claim was approved or published.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className={styles.page}>
      <div className={styles.shell}>
        <header className={styles.top}>
          <span className={styles.brand}>
            FR / FINANCIAL RESEARCH
          </span>
          <Link
            className={styles.back}
            href="/research/source-workspace/review"
          >
            ← Claim review
          </Link>
        </header>

        <section className={styles.hero}>
          <p className={styles.kicker}>
            M111 / LOCAL ANALYST DRAFT REVIEW
          </p>
          <h1>Write a claim. Examine its evidence.</h1>
          <p>
            恒瑞医药 · 2026 H1. Enter one proposed financial
            statement for bounded, source-linked review.
            This is a development experiment, not a
            financial-semantic certification.
          </p>
        </section>

        <div className={styles.grid}>
          <section className={styles.panel}>
            <p className={styles.section}>
              MANUAL ANALYST CANDIDATE
            </p>

            <label className={styles.field} htmlFor="draft">
              Financial claim
            </label>

            <textarea
              id="draft"
              className={styles.select}
              value={draft}
              maxLength={400}
              rows={5}
              disabled={busy}
              onChange={(event) => {
                setDraft(event.target.value);
                setResult(null);
                setError("");
              }}
              placeholder="Enter a proposed financial statement..."
            />

            <p className={styles.note}>
              {draft.length}/400 characters.
              The source and reviewer verdict are determined
              by the server, not by your input.
            </p>

            <button
              type="button"
              className={styles.button}
              disabled={busy || !draft.trim()}
              onClick={reviewDraft}
            >
              {busy ? "Reviewing source..." : "Review draft"}
            </button>
          </section>

          <aside className={styles.aside}>
            <p className={styles.section}>REVIEW LIMITATIONS</p>
            <h2>A bounded contradiction screen</h2>

            <div className={styles.item}>
              <strong>REJECT</strong>
              Recognized source contradiction
            </div>

            <div className={styles.item}>
              <strong>UNCERTAIN</strong>
              No independent financial-semantic approval
            </div>

            <div className={styles.item}>
              <strong>Publication</strong>
              Always BLOCKED
            </div>
          </aside>
        </div>

        {error && (
          <section className={styles.result} role="alert">
            <h2>Review withheld</h2>
            <p className={styles.warn}>{error}</p>
          </section>
        )}

        {result && (
          <section
            className={styles.result}
            aria-live="polite"
            aria-label="Manual Analyst review result"
          >
            <p className={styles.section}>
              UNPUBLISHED · CLAIM MC1
            </p>

            <h2>Review: {result.review.verdict}</h2>

            <article className={styles.claim}>
              <p className={styles.section}>ANALYST CANDIDATE</p>
              <p>{result.claim.text}</p>
              <p className={styles.muted}>
                Origin: {result.draft_origin}
              </p>
            </article>

            <article className={styles.claim}>
              <p className={styles.section}>REVIEW DECISION</p>
              <p><strong>{result.review.reason}</strong></p>
              <p className={styles.muted}>
                Scope: {result.review.review_scope}
              </p>
              <p className={styles.warn}>
                Financial semantics: NOT QUALIFIED.
                Publication: BLOCKED.
              </p>
            </article>

            <article className={styles.claim}>
              <p className={styles.section}>SOURCE EVIDENCE</p>
              <p>{result.evidence.excerpt}</p>
              <p className={styles.muted}>
                PDF page {result.evidence.source_page}
              </p>
              <p className={styles.muted}>
                Evidence ID: {result.evidence.evidence_id}
              </p>

              <a
                className={styles.source}
                href={`${result.source_url}#page=${result.evidence.source_page}`}
                target="_blank"
                rel="noopener noreferrer"
              >
                Open original disclosure ↗
              </a>
            </article>

            <details className={styles.claim}>
              <summary>Source and review identity</summary>
              <p className={styles.muted}>
                Document: {result.document_id}
              </p>
              <p className={styles.muted}>
                Source SHA-256: {result.source_sha256}
              </p>
              <p className={styles.muted}>
                Canonical SHA-256: {result.canonical_sha256}
              </p>
              <p className={styles.muted}>
                Review ID: {result.review_id}
              </p>
              <p className={styles.muted}>
                As-of: {result.as_of}
              </p>
            </details>
          </section>
        )}

        <p className={styles.note}>
          Local-only manual review. No model request,
          financial approval, trading action or publication.
        </p>
      </div>
    </main>
  );
}
