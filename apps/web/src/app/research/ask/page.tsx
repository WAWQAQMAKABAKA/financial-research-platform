import { Suspense } from "react";
import Link from "next/link";

const example = "What do the revenue and cost rows in the 2026H1 segment table say?";
const documentId = "600760-2026H1-cninfo-1225517994";

type Claim = { claim_id: string; text: string; evidence_ids: string[] };
type Review = { claim_id: string; verdict: string; rationale: string };
type Evidence = { evidence_id: string; page_number: number; excerpt: string };
type Answer = {
  status: string;
  reason?: string;
  answer_scope: string;
  research_publication: string;
  financial_semantic_review?: string;
  document_id?: string;
  question?: string;
  answer_id?: string;
  generated_at?: string;
  source_url?: string;
  source_sha256?: string;
  canonical_sha256?: string;
  claims: Claim[];
  reviews: Review[];
  evidence: Evidence[];
  limitation?: string;
};

async function QuestionResult({ searchParams }: {
  searchParams: Promise<{ q?: string | string[] }>;
}) {
  const params = await searchParams;
  const question = typeof params.q === "string" ? params.q : "";
  if (!question) return <p>Enter the supported question above to inspect the verified source.</p>;
  if (question.length > 240) return <p>Question too long. No answer released.</p>;

  let data: Answer | null = null;
  try {
    const base = process.env.RESEARCH_API_BASE_URL ?? "http://127.0.0.1:8000";
    const response = await fetch(`${base}/api/v1/research/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
      cache: "no-store",
    });
    if (response.ok) data = (await response.json()) as Answer;
  } catch {
    data = null;
  }

  if (data?.status === "UNSUPPORTED") {
    return <p>Unsupported question. No answer released. This prototype supports only the example question.</p>;
  }
  if (
    data === null || data.status !== "SOURCE_ANSWER_READY" ||
    data.answer_scope !== "SOURCE_TEXT_ONLY" ||
    data.research_publication !== "BLOCKED" ||
    data.financial_semantic_review !== "NOT_PERFORMED" ||
    data.document_id !== documentId ||
    !Array.isArray(data.claims) || data.claims.length !== 2 ||
    !Array.isArray(data.reviews) || data.reviews.length !== 2 ||
    !Array.isArray(data.evidence) || data.evidence.length !== 2 ||
    data.reviews.some((r) => r.verdict !== "ADMIT") ||
    new Set(data.claims.map((c) => c.claim_id)).size !== 2 ||
    new Set(data.reviews.map((r) => r.claim_id)).size !== 2 ||
    new Set(data.evidence.map((e) => e.evidence_id)).size !== 2 ||
    data.claims.some((c) =>
      typeof c.text !== "string" ||
      !Array.isArray(c.evidence_ids) || c.evidence_ids.length !== 1 ||
      !data?.reviews.some((r) => r.claim_id === c.claim_id) ||
      !data?.evidence.some((e) => e.evidence_id === c.evidence_ids[0] && e.page_number === 198)
    ) ||
    typeof data.source_url !== "string" ||
    data.source_url !== "https://static.cninfo.com.cn/finalpage/2026-08-28/1225517994.PDF"
  ) return <p>Answer: UNAVAILABLE — no unverified claims displayed.</p>;

  return (
    <section aria-label="Source-only answer" style={{ marginTop: 28 }}>
      <h2>Source-only answer</h2>
      <p><strong>Literal source transcription — NOT a reviewed financial conclusion.</strong></p>
      {data.claims.map((claim) => {
        const review = data.reviews.find((r) => r.claim_id === claim.claim_id);
        const item = data.evidence.find((e) => e.evidence_id === claim.evidence_ids[0]);
        if (!review || !item || item.page_number !== 198) return null;
        return (
          <article key={claim.claim_id} style={{ border: "1px solid #888", borderRadius: 8, padding: 14, marginTop: 16 }}>
            <p>{claim.text}</p>
            <p>Review: {review.verdict} (literal source text only)</p>
            <p>Evidence: {item.evidence_id} · PDF page {item.page_number}</p>
            <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", fontFamily: "inherit" }}>{item.excerpt}</pre>
            <a href={`${data.source_url}#page=${item.page_number}`} target="_blank" rel="noopener noreferrer">
              Open original CNINFO PDF — page {item.page_number}
            </a>
          </article>
        );
      })}
      <h3>Provenance</h3>
      <p style={{ overflowWrap: "anywhere" }}>Answer ID: {data.answer_id}</p>
      <p style={{ overflowWrap: "anywhere" }}>PDF SHA-256: {data.source_sha256}</p>
      <p style={{ overflowWrap: "anywhere" }}>Canonical SHA-256: {data.canonical_sha256}</p>
      <p>Generated: {data.generated_at}</p>
      <p><strong>Research publication: BLOCKED.</strong> Financial-semantic review: NOT PERFORMED.</p>
      <p>Limitation: {data.limitation}</p>
    </section>
  );
}

export default function AskPage({ searchParams }: {
  searchParams: Promise<{ q?: string | string[] }>;
}) {
  return (
    <main style={{ maxWidth: 880, margin: "50px auto", padding: 24, fontFamily: "Arial, sans-serif" }}>
      <Link href="/research">Back to research</Link>
      <h1>Ask a financial disclosure</h1>
      <p>Development prototype: one supported question, one verified report, literal source text only.</p>
      <form method="get" action="/research/ask" style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <input aria-label="Research question" name="q" type="text" defaultValue={example}
          maxLength={240} required style={{ flex: "1 1 350px", padding: 12, border: "1px solid #888", borderRadius: 8 }} />
        <button type="submit" style={{ padding: 12, border: "1px solid #888", borderRadius: 8 }}>Ask</button>
      </form>
      <Suspense fallback={<p>Verifying source and reviewing claims...</p>}>
        <QuestionResult searchParams={searchParams} />
      </Suspense>
    </main>
  );
}
