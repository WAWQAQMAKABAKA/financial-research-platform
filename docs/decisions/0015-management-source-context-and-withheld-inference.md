# ADR 0015 — M1.8B management source context and withheld inference

Date: 2026-10-22
Status: PROPOSED — Mac original-PDF audit, offline regression and Safari acceptance pending.

## Narrow visible slice

For the pinned **恒瑞医药 600276 2026H1** report, keep the two
native-PDF-verified income-statement revenue cells (consolidated and parent)
and add a third, management-discussion passage about innovative-drug sales.
The selection is anchored in the report's management-discussion section by a
non-numeric topical phrase; numerical substrings are extracted from the
original report, not embedded as reference answers. The source is SHA-pinned,
PIT-gated and retained only on the local developer machine. No legacy source
repository, benchmark ground truth, or trading state is touched.

The local-only page `/research/source-workspace/analyse` shows three separately
identified and cited **literal source observations**, each with its own
Reviewer record, plus `A1` marked **WITHHELD_UNQUALIFIED_INFERENCE**.
A single explicit DeepSeek Flash request proposes JSON bindings for F1, F2,
M1 and an Analyst hypothesis. All three factual claim strings, IDs, order,
and evidence IDs must match independently constructed source packets exactly.
The Analyst hypothesis is NEVER serialized into the result or browser. The
browser renders deterministic factual formatting; this is **not** approved
natural-language financial-semantic interpretation.

## Independent check, not accounting certification

- The two income-statement cells reuse `revenue_scope.build_source_draft`,
  requiring original SHA/canonical SHA, PIT, table-cell attribution and a
  native-PDF location Reviewer.
- The management source is selected via a unique section-anchored literal
  sentence in the same SHA-qualified PDF; a second native word extraction
  must confirm co-located text. Whitespace normalization does not assert
  accounting or management truth.
- The model does not choose PDF pages, create a financial metric, revise a
  source value, or set a review verdict. Source text is treated as untrusted.
- `MANAGEMENT_STATEMENT` is an attribution to a filed management-discussion
  passage. It is not treated as an independently validated causal explanation.
- `ANALYST_INFERENCE` remains WITHHELD, with no text returned. Real
  interpretation will require future financial-semantic qualification.

## Paid-call and publication boundaries

The existing development-only loopback Next.js broker, ephemeral server token,
secret handling and FastAPI four-attempt budget are reused. PDF work is
serialized and finishes before any network model call; no retry. Source
failure does not debit the paid attempt counter. All responses retain
`financial_semantic_review=NOT_PERFORMED` and
`research_publication=BLOCKED`.

## Acceptance

1. Pre-write clean `main` at committed M1.8A HEAD, FF-only pull, exact patch
   scope; no hidden files, keys, raw PDFs or GT committed.
2. Full offline backend regression; Next.js build, TypeScript and ESLint.
3. Read-only original Hengrui PDF audit: 2 independent source cells and one
   uniquely section-anchored management passage with independent word check.
4. One opt-in DeepSeek browser call; F1/F2/M1 each with distinct evidence ID,
   source URL/page and independent literal-only review; A1 must be withheld.
5. Production configuration and unauthenticated HTTP paths fail closed.
6. Commit/push only after actual browser acceptance; remote HEAD verified.
