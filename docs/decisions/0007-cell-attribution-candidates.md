# ADR 0007 — Unreviewed financial-table cell attribution

Date: 2026-10-20
Status: PROPOSED — pending original-source audit on two issuers

## Purpose

Build a narrow, offline, source-located table-cell candidate layer above
`index_document`. This is **not** a numeric-reasoning engine, accounting
normalizer, analyst model, semantic reviewer, or customer publication channel.

A candidate is scoped by discovered statement type, verbatim source row label,
and verbatim root-table column header. It carries document and canonical hashes,
PIT-eligible source identity, section candidate relationship, page/table/row/
column indices, cell coordinates, and raw text. A selector may return only one
match. Missing or duplicate row/column matches fail closed to `UNRESOLVED`.

`locate_cells_in_verified_pdf` rebuilds the document index from a hash-verified
PDF once per batch. It also captures source-printed period/unit/currency context
from the statement heading region, **verbatim and without interpretation**.

## Explicit non-claims

- A geometry-derived column header is not independently verified financial
  period semantics; a heading candidate is not a certified consolidated scope.
- A blank, missing, and printed dash are not automatically the numeric value 0.
- A raw amount, even a correct amount, cannot authorize a trend, comparison,
  gross margin, investment opinion, or claim-level `ADMIT`.
- Table-cell rectangles are **not** canonical character offsets. Do not create
  `EvidenceSpan` values with guessed canonical offsets.
- A serialized index is not an authenticated source; regenerate from the
  expected hash-qualified PDF before using cell candidates.
- Continuation links remain geometric candidates, without semantic merging.
- Current code has no API route, customer UI, LLM agent, or publication rights;
  `research_publication` remains `BLOCKED`.

## Isolation and development qualification

Production-path files contain no issuer-specific numbers, page locations, or
benchmark labels. Synthetic tests check PIT, source identity, scope and period
separation, blanks/dashes/negative values, duplicate/missing bindings and fail-
closed behavior. Independent **offline-only** source checks for 600760 and
600276 are not copied into the repository or imported by the runtime.

## Carryforward lessons

Historical Hengrui C4 incorrectly compared unlike drug-category shares despite
correct-looking citations and Reviewer approval. These contracts therefore
preserve source row and column association without authorizing metric identity
or financial comparability. The next acceptance gate must be independent
financial-semantic review, not string matching or a framework-generated score.

No trading state, legacy repo dependency, protected GT, or source PDF is added.
