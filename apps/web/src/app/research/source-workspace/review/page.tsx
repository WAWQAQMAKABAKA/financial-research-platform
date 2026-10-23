"use client";

import Link from "next/link";
import { useState } from "react";
import styles from "../ask/ask.module.css";

const SOURCE = {
  documentId: "600276-2026H1-cninfo-1225483600",
  url: "https://static.cninfo.com.cn/finalpage/2026-08-20/1225483600.PDF",
  sourceSha: "ff6910663a9726acb889aa061a8bab1433f58890d81ebea013b8c637a097a7aa",
  canonicalSha: "96784f9deba244aab85bd117b9a1894bdcbd689a8368554f84014703f1e8b864",
} as const;

const OPTIONS = [
  {
    code: "share_company_revenue",
    label: "Revenue-share denominator substitution",
    verdict: "REJECT",
    reason: "SOURCE_SHARE_DENOMINATOR_SUBSTITUTED",
    explanation: "The management passage identifies drug sales revenue as the denominator, not total consolidated company revenue.",
  },
  {
    code: "share_drug_sales",
    label: "Source-aligned revenue-share wording",
    verdict: "UNCERTAIN",
    reason: "SOURCE_SHARE_NOT_FINANCIALLY_QUALIFIED",
    explanation: "The wording follows the management passage, but attribution alone cannot certify its financial meaning.",
  },
  {
    code: "growth_company_revenue",
    label: "Company-wide growth substitution",
    verdict: "REJECT",
    reason: "SOURCE_GROWTH_METRIC_SUBSTITUTED",
    explanation: "The source percentage describes innovative-drug sales growth, not consolidated company revenue growth.",
  },
  {
    code: "growth_innovative_drugs",
    label: "Source-aligned innovative-drug growth",
    verdict: "UNCERTAIN",
    reason: "SOURCE_GROWTH_NOT_FINANCIALLY_QUALIFIED",
    explanation: "This wording is source-aligned but has not undergone independent accounting-semantic qualification.",
  },
] as const;

type ClaimCode = (typeof OPTIONS)[number]["code"];

type ReviewPacket = {
  status: string;
  report_key: string;
  claim_code: ClaimCode;
  claim_id: string;
  claim_text: string;
  preview_id: string;
  document_id: string;
  source_url: string;
  source_sha256: string;
  canonical_sha256: string;
  financial_semantic_review: string;
  research_publication: string;
  review: {
    claim_id: string;
    verdict: string;
    reason: string;
    compared_evidence_ids: string[];
  };
  evidence: {
    evidence_id: string;
    page: number;
    excerpt: string;
    review_scope: string;
  };
};

const PASSAGE =
  /^2026年上半年公司创新药销售收入\d+(?:\.\d+)?亿元，同比增长(\d+(?:\.\d+)?)%，占药品销售收入的比重达(\d+(?:\.\d+)?)%[。]$/u;

function expectedText(
  code: ClaimCode,
  growth: string,
  share: string,
): string {
  switch (code) {
    case "share_company_revenue":
      return `Innovative-drug sales were ${share}% of total consolidated company revenue.`;
    case "share_drug_sales":
      return `Innovative-drug sales were ${share}% of drug sales revenue.`;
    case "growth_company_revenue":
      return `Total consolidated company revenue grew ${growth}% year over year.`;
    case "growth_innovative_drugs":
      return `Innovative-drug sales grew ${growth}% year over year.`;
  }
}

function verified(
  value: unknown,
  requested: ClaimCode,
): value is ReviewPacket {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return false;
  }

  const a = value as Partial<ReviewPacket>;
  const option = OPTIONS.find((entry) => entry.code === requested);
  if (!option || !a.review || !a.evidence) return false;

  const r = a.review;
  const e = a.evidence;

  if (
    a.status !== "LOCAL_CLAIM_REVIEW_READY" ||
    a.report_key !== "600276-2026H1" ||
    a.claim_code !== requested ||
    a.claim_id !== "C1" ||
    a.document_id !== SOURCE.documentId ||
    a.source_url !== SOURCE.url ||
    a.source_sha256 !== SOURCE.sourceSha ||
    a.canonical_sha256 !== SOURCE.canonicalSha ||
    a.research_publication !== "BLOCKED" ||
    a.financial_semantic_review !== "NOT_QUALIFIED" ||
    typeof a.preview_id !== "string" ||
    !/^[0-9a-f]{64}$/.test(a.preview_id) ||
    r.claim_id !== "C1" ||
    r.verdict !== option.verdict ||
    r.reason !== option.reason ||
    typeof e.evidence_id !== "string" ||
    !/^[0-9a-f]{64}$/.test(e.evidence_id) ||
    e.page !== 20 ||
    e.review_scope !== "NATIVE_PDF_TEXT_AND_WORD_LOCATION_ONLY" ||
    !Array.isArray(r.compared_evidence_ids) ||
    r.compared_evidence_ids.length !== 1 ||
    r.compared_evidence_ids[0] !== e.evidence_id ||
    typeof e.excerpt !== "string" ||
    typeof a.claim_text !== "string"
  ) {
    return false;
  }

  const match = PASSAGE.exec(e.excerpt);
  if (!match) return false;

  return a.claim_text === expectedText(
    requested,
    match[1],
    match[2],
  );
}

export default function LocalClaimReviewPage() {
  const [code, setCode] = useState<ClaimCode>("share_company_revenue");
  const [result, setResult] = useState<ReviewPacket | null>(null);
  const [reviewedCode, setReviewedCode] = useState<ClaimCode | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function reviewClaim() {
    if (busy) return;

    const requested = code;
    setBusy(true);
    setResult(null);
    setReviewedCode(null);
    setError("");

    try {
      const response = await fetch("/api/local-claim-review", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          report_key: "600276-2026H1",
          claim_code: requested,
        }),
        cache: "no-store",
      });

      if (!response.ok) throw new Error("LOCAL_UNAVAILABLE");

      const packet: unknown = await response.json();
      if (!verified(packet, requested)) {
        throw new Error("UNQUALIFIED_PACKET");
      }

      setResult(packet);
      setReviewedCode(requested);
    } catch {
      setError(
        "Claim review unavailable. The original source, local API or review contract could not be verified. No conclusion was released.",
      );
    } finally {
      setBusy(false);
    }
  }

  const detail = OPTIONS.find((option) => option.code === reviewedCode);

  return (
    <main className={styles.page}>
      <div className={styles.shell}>
        <header className={styles.top}>
          <span className={styles.brand}>FR / FINANCIAL RESEARCH</span>
          <Link className={styles.back} href="/research/source-workspace">
            ← Source workspace
          </Link>
        </header>

        <section className={styles.hero}>
          <p className={styles.kicker}>
            M1.9C / LOCAL CLAIM-LEVEL REVIEW
          </p>
          <h1>Inspect the claim. Follow the evidence.</h1>
          <p>
            恒瑞医药 · 2026 H1 · Four bounded financial claim formulations,
            independently checked against the original disclosure.
            No model call, financial approval or publication.
          </p>
        </section>

        <div className={styles.grid}>
          <section
            className={styles.panel}
            aria-label="Select financial claim"
          >
            <p className={styles.section}>CLAIM REVIEW PREVIEW</p>
            <label htmlFor="claim-code" className={styles.field}>
              Select one claim formulation
            </label>

            <select
              id="claim-code"
              className={styles.select}
              value={code}
              disabled={busy}
              onChange={(event) => {
                setCode(event.target.value as ClaimCode);
                setResult(null);
                setReviewedCode(null);
                setError("");
              }}
            >
              {OPTIONS.map((option) => (
                <option key={option.code} value={option.code}>
                  {option.label}
                </option>
              ))}
            </select>

            <p className={styles.note}>
              The claim percentage is filled from the verified PDF,
              not from a reference answer embedded in the interface.
            </p>

            <button
              type="button"
              className={styles.button}
              disabled={busy}
              onClick={reviewClaim}
            >
              {busy ? "Checking the original PDF…" : "Review this claim"}
            </button>

            <p className={styles.note}>
              Local development only. No DeepSeek request and no usage charge.
            </p>
          </section>

          <aside className={styles.aside}>
            <p className={styles.section}>REVIEW BOUNDARY</p>
            <h2>Contradiction detection is not certification.</h2>
            <div className={styles.item}>
              <strong>REJECT</strong>
              Explicit contradiction with source-bound wording
            </div>
            <div className={styles.item}>
              <strong>UNCERTAIN</strong>
              Meaning remains unqualified, even if source-aligned
            </div>
            <div className={styles.item}>
              <strong>Research publication</strong>
              BLOCKED for every result
            </div>
          </aside>
        </div>

        {error && (
          <section className={styles.result} role="alert">
            <h2>Review withheld</h2>
            <p className={styles.warn}>{error}</p>
          </section>
        )}

        {result && detail && (
          <section
            className={styles.result}
            aria-live="polite"
            aria-label="Claim-level review result"
          >
            <p className={styles.section}>
              UNPUBLISHED · CLAIM C1 · REVIEW TRACE
            </p>

            <h2>Reviewer: {result.review.verdict}</h2>

            <article className={styles.claim}>
              <p className={styles.section}>CLAIM BEING REVIEWED</p>
              <p>{result.claim_text}</p>
              <p className={styles.muted}>
                Claim ID: {result.claim_id}
              </p>
            </article>

            <article className={styles.claim}>
              <p className={styles.section}>REVIEW EXPLANATION</p>
              <p>
                <strong>{result.review.reason}</strong>
              </p>
              <p>{detail.explanation}</p>
              <p className={styles.muted}>
                Verdict: {result.review.verdict} ·
                Financial semantics: NOT QUALIFIED
              </p>
            </article>

            <article className={styles.claim}>
              <p className={styles.section}>
                SOURCE EVIDENCE · ORIGINAL DISCLOSURE
              </p>
              <p>{result.evidence.excerpt}</p>
              <p className={styles.muted}>
                PDF page {result.evidence.page} · Evidence ID:
                {" "}{result.evidence.evidence_id}
              </p>

              <a
                className={styles.source}
                href={`${result.source_url}#page=${result.evidence.page}`}
                target="_blank"
                rel="noopener noreferrer"
              >
                Open original PDF · Page {result.evidence.page} ↗
              </a>
            </article>

            <details className={styles.claim}>
              <summary>Document provenance and review identity</summary>
              <p className={styles.muted}>
                Document: {result.document_id}
              </p>
              <p className={styles.muted}>
                Original PDF SHA-256: {result.source_sha256}
              </p>
              <p className={styles.muted}>
                Canonical SHA-256: {result.canonical_sha256}
              </p>
              <p className={styles.muted}>
                Preview ID: {result.preview_id}
              </p>
            </details>

            <p className={styles.warn}>
              Financial-semantic approval: NOT QUALIFIED.
              Research publication: BLOCKED.
            </p>
          </section>
        )}

        <p className={styles.note}>
          Development-only preview. No trading, valuation, publication,
          or independent accounting qualification.
        </p>
      </div>
    </main>
  );
}
