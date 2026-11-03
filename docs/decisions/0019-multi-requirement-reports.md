# 0019 — Multi-requirement facts-only reports (M4)

Date: 2026-11-03
Status: accepted for M4 v1 (single document 600760, income-statement amounts)

## Context

M1–M3 answer one fact per question (with metric and statement-scope
clarification). Real research questions often ask for two or three facts:
"营业收入和净利润分别是多少？". Answering only the first facet, or rejecting the
question, loses information the source already supports.

## Decision

`evidence_plan.split_facets` splits a question on conjunctions (以及/并且/和/与/
及/、/，/；/and) into at most three facets. Every facet is resolved against the
verified table index with the statement scope of the whole question forced;
each requirement gets a coverage status:

- `SATISFIED` — exactly one literal row resolves;
- `AMBIGUOUS` — several rows resolve (no guess, no publication for that facet);
- `NO_ROW_MATCH` / other selection reason — the facet is not supported;
- `NOT_VERIFIED` — the row was found but failed location, literal review, or a
  blank/dash cell check.

Every satisfied row still goes through `locate_cells_in_verified_pdf`,
`review_literal` and `publication_policy`. The report publishes only verified
facts and includes a `coverage` block with total/satisfied and the status of each
requirement. A partial report is `REPORT_READY` with `coverage.complete = false`
and an explicit missing list; it never fills a gap by inference, comparison, or
prose.

The whole-question intent gate runs first, so "营业收入和净利润相比如何" is
rejected as a comparison before any facet is planned. If the whole question has
no statement title and both statements hold matching rows, the existing
statement-scope clarification is offered instead of planning.

Route selection: `POST /reports/{key}/ask` checks `split_facets`; two or more
facets use `build_multi_report`, otherwise the single-fact path is unchanged.

## Bounded repair (v1)

A partial report may carry one optional repair suggestion for the first missing
requirement. The candidates are the verified rows of the same statement that
share a rare lexical bigram with the missing facet; a signed, expiring token is
returned with them. Nothing is published from the suggestion: the user chooses a
row, the report is rebuilt with that row pinned, and the row still goes through
location, literal review and the policy. There is no automatic statement switch
and no second repair round. If no candidate matches, the partial report is
returned unchanged.

This is a user-confirmed lexical repair, not semantic equivalence: "研发投入" may
be offered "研发费用" as a candidate, and the user decides.

## Deliberately not implemented

- Multi-source requirements (management discussion text) and cross-page
  assembly beyond the table index.
- Comparisons, causal explanations, forecasts and any inferential composition.
- More than three facets; longer questions fall back to the single-fact path.

## Consequences

- The UI renders a coverage section (satisfied/total, per-facet status) next to
  the verified facts.
- A multi-fact question can return two facts from the same statement; duplicates
  are de-duplicated before location.
- `coverage` is informational; publication authority remains
  `publication_policy.decide_publication`.

## LLM facet proposal (v3)

An opt-in DeepSeek call may propose the 2–3 facets for a multi-fact question
(`FRP_LOCAL_CLARIFY_LLM=1` + `DEEPSEEK_API_KEY`, budget 4 per process). The
proposal is untrusted: facets must be unique Chinese phrases of 2–120
characters, and every facet is still resolved through the deterministic row
matching, location, literal review and policy. An invalid, unavailable or
over-budget proposal falls back to the conjunction split. `coverage.plan_source`
records which path was used; the page shows it. Repair rebuilds never call the
model.
