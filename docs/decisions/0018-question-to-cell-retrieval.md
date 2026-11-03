# 0018 — M2a: question to table row to verified cell

Date: 2026-11-02
Status: accepted for M2a (single document 600760, income-statement amounts)

## Context

M1 published a facts-only report, but the row it published was configured per
document in `source_workspace.SELECTIONS` (`其中：营业收入`, `2026 年半年度`).
That proved the publication gate, not a copilot: the user's question selected
nothing. The repository already had a generic lexical retriever
(`canonical_retrieval`) and a verified table index (`document_index`), but the
report path did not use them.

## Decision

`question_selection.select_cells` derives a selection from the question and the
document's own structure. No model is called.

1. **Statement scope** — from the statement-title contract (`SECTION_TITLES`:
   合并利润表 / 母公司利润表) when the question names one. If the question names
   none, the ranked retrieval pages may decide, but only with a 2× margin, and
   the response records `selection_basis = RETRIEVAL_PAGE_PRIORITY` so the
   inferred scope is visible. Two named statements are ambiguous and withheld.
2. **Reporting column** — from the manifest reporting period
   (`2026H1` → `2026 年半年度`). The column must exist exactly once.
3. **Rows** — from the verified table index of that statement. Row labels are
   matched after stripping enumeration (`一、`, `（一）`, `其中：`, `1.`) and
   trailing filing annotations (`（净亏损以“-”号填列）`). Matching is literal
   containment of the row core in the question; the located label stays
   verbatim.
4. **Cells** — each selected row is located by `locate_cells_in_verified_pdf`
   (bounded table scan), re-checked by `review_literal` against native PDF text
   and geometry, and then passed to `publication_policy` with the exact set of
   selected labels.
5. **Blank and dash are not zero** — the report is withheld with
   `SOURCE_CELL_BLANK_NOT_ZERO` or `SOURCE_CELL_DASH_NOT_ZERO`.

Fail-closed reasons are visible to the reader:
`OUT_OF_PERIOD_SCOPE`, `NO_STATEMENT_SCOPE`, `AMBIGUOUS_STATEMENT_SCOPE`,
`COLUMN_HEADER_UNAVAILABLE`, `NO_ROW_MATCH`, `TOO_MANY_ROW_MATCHES`,
`SOURCE_CELL_UNRESOLVED`, `SOURCE_CELL_AMBIGUOUS`,
`LITERAL_REVIEW_NOT_PASSED`.

Withheld responses carry the retrieval trace **without source excerpts**, so a
failed question cannot display a number from a neighbouring statement.

## Deliberately not solved

- Cross-period and prior-year columns (`2025 年半年度`) are out of scope.
- Comparisons, inferences and management explanations remain withheld.
- Metric identity is still lexical: 营业收入 matches the literal row, not a
  certified accounting concept.
- One document (600760). A second document requires its own manifest entry and
  independent identity verification.
- A question naming two statements, or no statement without a decisive retrieval
  margin, is withheld rather than guessed.

## Consequences

- The report page accepts `?q=` and renders the retrieval trace, the selection
  basis, and one card per published row.
- `publication_policy.decide_publication` accepts an explicit set of expected
  row labels; a claim for a label the caller did not select is still a
  `SELECTION_MISMATCH`.
- Response time drops to roughly 12–25 seconds per question because the table
  scan is bounded to the selected statement kinds.
