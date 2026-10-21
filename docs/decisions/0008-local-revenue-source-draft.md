# ADR 0008 — Local-only source-cited revenue draft

Date: 2026-10-21
Status: PROPOSED — local integration and browser verification pending

## One visible slice

Hengrui (600276), 2026H1: show the verbatim revenue cells from the
consolidated and parent-company income statements **separately**. This is
not a comparison, a reviewed CAS accounting conclusion, or a published report.
The question-specific row selections and official CNINFO source metadata are
local demo configuration, not expected numeric answers or parser geometry.

## Evidence / review path

The API rebuilds the whole-document index from the original hash-qualified PDF
with PIT checked against the published-on date and pinned canonical SHA.
`locate_cells_in_verified_pdf` provides table-cell candidates (no canonical
character offsets). The bounded Analyst drafts one literal claim per cell.
A separate native-PDF location Reviewer checks the original text at the
provided cell/row rectangles and the printed heading, period, column and
unit/currency context. Reviewer `ADMIT` means **literal-location only**.
It does not certify accounting comparability or financial semantics.

Any missing source, suspicious geometry, ambiguous lookup or failed literal
check withholds all observations. The new GET route is disabled unless
`FRP_LOCAL_REVENUE_PREVIEW=1` and the source path is explicitly configured.
Next.js renders a labeled draft and links to the original PDF pages, but also
requires the publication gate to remain `BLOCKED`. It does not present a
consolidated-minus-parent comparison, causal explanation, valuation or trade.

## Remaining qualification

This ADR does not authorize production exposure. Before calling the slice
VERIFIED: run backend regression; original-182-page offline source references;
verify API disabled, positive and source-failure paths; build Next.js; inspect
browser citations and blocked status. Independent financial-semantic assessment
and customer publication are further gates. The offline audit values and
protected evaluation ground truth remain outside runtime/repository.
