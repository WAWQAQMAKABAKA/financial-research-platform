# ADR 0011 — Two-issuer source-only research workspace

Date: 2026-10-21
Status: PROPOSED — local original-PDF and browser acceptance pending

## Customer-visible slice

Reuse the existing full-document index and source-located cell resolver for
both 600276 (恒瑞医药) and 600760 (中航沈飞), 2026H1, with **one consolidated
revenue observation per selected report**. One allowlisted API route and one
Next.js page serve both issuers. The previously verified Hengrui two-scope
preview remains unchanged. No numerical benchmark labels, original PDFs, or
ground truth are committed to the repository.

The report registry pins each `SourceDocument` to existing source and canonical
hashes, report date and official URL, with a question-specific statement type,
row and literal column label. It contains no expected numbers, page coordinates
or canonical offsets. An issuer cannot choose an arbitrary local PDF path:
`FRP_LOCAL_SOURCE_WORKSPACE=1` and the server-controlled per-issuer PDF-path
environment variables are required. Requests to unknown issuers fail closed.

The shared extraction path regenerates the full-document index and calls the
native-PDF independent literal-cell reviewer. A matched amount must still be
printed verbatim in the original report. The scope is restricted to the 2026 H1
CNY consolidated-income-statement vocabulary already qualified in development;
it is not a generic statement interpreter or a free-form company search.

## Safety boundary

The source-only observation is displayed separately for the selected issuer.
No cross-company comparison, growth rate, causal explanation, trading
recommendation, semantic `ADMIT` or published research report is authorized.
`research_publication=BLOCKED`; `financial_semantic_review=NOT_PERFORMED`.
PDF geometry is not a canonical character offset. The source PDF hash and
point-in-time availability must be verified before showing numbers.

## Qualification

Network-free synthetic adversarial tests must pass; independent offline
references verify selected real cells against each original full PDF; API route
must be off by default and fail closed; Next.js build and lint must pass; and
Safari must display the exact PDF page links for both issuers. This is
**development qualification for two reports**, not broad Chinese-market
accuracy or financial-semantic certification. Expand the reference set before
expanding the financial topics.
