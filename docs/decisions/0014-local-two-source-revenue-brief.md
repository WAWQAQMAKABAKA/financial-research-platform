# ADR 0014 — M1.8A Hengrui two-source evidence briefing

Date: 2026-10-22
Status: PROPOSED — Mac offline and original-document verification pending

## Narrow customer-visible slice

`/research/source-workspace/explain` asks one supported Hengrui 2026 H1
question about **two revenue-labelled rows** from the consolidated and
parent-company income statements. Every displayed numerical fact has its own
claim ID, evidence ID, original CNINFO PDF-page link and literal-review record.
The interface explicitly labels the brief as document structure, **not** an
accounting conclusion or financial explanation. No comparative arithmetic,
growth, causal story, valuation or trades are permitted.

## Trust and cost boundary

Reuse the existing pinned-source `revenue_scope.build_source_draft`: PIT,
original PDF and canonical SHA checks, full-document table attribution,
and independent native-PDF literal location review **for both cells**.
Reuse `deepseek_draft.draft_verified_cells` to ask DeepSeek for exact JSON
source bindings, not free-form financial prose. Code synthesizes all displayed
sentences from reviewed evidence; model text cannot become a published claim.
Both claims are withheld if either source or model claim fails binding.

The local-only Next.js broker and FastAPI session-token guard remain required.
Only the Hengrui report supports this question. A button explicitly authorizes
one paid request; no retries, at most four attempts per local server process.
No benchmark ground truth or expected report values are placed in runtime.

## Acceptance before commit

Install only against baseline `f85a570ded0e458f6897b8e8f14eae7fc5feee29`
with clean `main` and `git pull --ff-only`. Verify all offline tests, build,
lint, guards and exact patch scope. The Mac original PDF must produce two
independently accepted literal evidence items; synthetic tests do not count
as original-document qualification. Then test one explicit paid DeepSeek
request in Safari, two source-page links, two distinct evidence IDs, and
`financial_semantic_review=NOT_PERFORMED` / `research_publication=BLOCKED`.
This ADR alone does not authorize a production customer report.
