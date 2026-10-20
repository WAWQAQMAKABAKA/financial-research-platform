import { Suspense } from "react";
import Link from "next/link";

type EvidenceItem = {
  evidence_id: string;
  page_number: number;
  canonical_start: number;
  canonical_end: number;
  excerpt: string;
};

type Preview = {
  status: string;
  document_id: string;
  ticker: string;
  report_period: string;
  source_url: string;
  source_sha256: string;
  canonical_sha256: string;
  financial_semantic_review: string;
  evidence: EvidenceItem[];
  limitation: string;
};

async function EvidenceContent() {
  const baseUrl = process.env.RESEARCH_API_BASE_URL ?? "http://127.0.0.1:8000";
  let result: Preview | null = null;
  try {
    const response = await fetch(
      `${baseUrl}/api/v1/research/evidence-preview/600760-2026H1-cninfo-1225517994`,
      { cache: "no-store" },
    );
    if (response.ok) {
      result = (await response.json()) as Preview;
    }
  } catch {
    result = null;
  }
  if (
    result === null ||
    result.status !== "SOURCE_EVIDENCE_ONLY" ||
    result.document_id !== "600760-2026H1-cninfo-1225517994" ||
    result.financial_semantic_review !== "NOT_PERFORMED" ||
    !Array.isArray(result.evidence) || result.evidence.length !== 2 ||
    result.evidence.some((item) => item.page_number !== 198)
  ) return <p>Source preview: UNAVAILABLE</p>;

  return (
    <section>
      <h2>Verified source evidence</h2>
      <p>Ticker: {result.ticker} · Reporting period: {result.report_period}</p>
      <p><strong>SOURCE EVIDENCE ONLY — NOT FINANCIAL RESEARCH</strong></p>
      {result.evidence.map((item) => (
        <article key={item.evidence_id} style={{
          border: "1px solid #888", borderRadius: 8, padding: 16, marginTop: 20,
        }}>
          <h3>{item.evidence_id}</h3>
          <p>PDF page {item.page_number} · Canonical offsets {item.canonical_start}–{item.canonical_end}</p>
          <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", fontFamily: "inherit" }}>
            {item.excerpt}
          </pre>
          <a href={`${result.source_url}#page=${item.page_number}`} target="_blank" rel="noopener noreferrer">
            Open original CNINFO PDF — page {item.page_number}
          </a>
        </article>
      ))}
      <h3>Evidence integrity</h3>
      <p style={{ overflowWrap: "anywhere" }}>Document ID: {result.document_id}</p>
      <p style={{ overflowWrap: "anywhere" }}>PDF SHA-256: {result.source_sha256}</p>
      <p style={{ overflowWrap: "anywhere" }}>Canonical SHA-256: {result.canonical_sha256}</p>
      <p><strong>Limitation:</strong> {result.limitation}</p>
    </section>
  );
}

export default function EvidencePage() {
  return (
    <main style={{ maxWidth: 880, margin: "60px auto", padding: 24, fontFamily: "Arial, sans-serif" }}>
      <Link href="/research">Back to research</Link>
      <h1>Financial Research Platform</h1>
      <p>Development evidence preview</p>
      <Suspense fallback={<p>Verifying source...</p>}>
        <EvidenceContent />
      </Suspense>
    </main>
  );
}
