# M4 Experiment — multi-requirement coverage baseline (v1)

**Status: PASS.** 8/8 interpretations correct, 0 unsafe publications, 0
false-sufficient coverage, coverage recall 1.0.

- Questions SHA-256: `9aa1a2e991559c5c46532d0dae94533b72554292b4a43f7f7d345fa78ab7a887`
- Source: `600760-2026H1-cninfo-1225517994`, source `d53ee98c…`, canonical `620d3a30…`, 207 pages
- Runtime under test: git `79eb718`
- Capture run at `01dcd88`, private and untracked
- 8 author-curated development cases, not an independent holdout

## Protocol

Capture drives the unmodified `POST /api/v1/research/reports/{key}/ask` route with
a local token and does not read expectations. Score reads the frozen set and
compares published cells, coverage completeness, missing-requirement status and
unsafe publications.

```zsh
RUN="data/private/m4-multi-eval/run_$(date -u +%Y%m%dT%H%M%SZ)"
.venv/bin/python evaluations/offline/run_m4_multi_eval.py verify-questions \
  --pdf data/raw/600760/2026H1/source.pdf
.venv/bin/python evaluations/offline/run_m4_multi_eval.py capture \
  --pdf data/raw/600760/2026H1/source.pdf --run-dir "$RUN"
.venv/bin/python evaluations/offline/run_m4_multi_eval.py score --run-dir "$RUN"
```

`verify-questions` reported `OK expectation cross-check (0 failure(s))` for the
ten expected cells.

## Scorecard

| Metric | Value |
|---|---|
| Cases | 8 |
| Correct interpretations | **8/8 = 1.0** |
| **Unsafe publications** (gate) | **0** |
| False rejections | 0 |
| Unexpected clarifications | 0 |
| Guessed scope | 0 |
| Clarify missed | 0 |
| Coverage recall | **1.0** |
| **False sufficient coverage** | **0** |
| Missing-status accuracy | **1.0** |
| Latency avg / max | 10.1 s / 16.2 s |

## Per-case results

| Case | Family | Result |
|---|---|---|
| M4-01 | two facts | CORRECT_COVERAGE (2/2) |
| M4-02 | three facts | CORRECT_COVERAGE (3/3) |
| M4-03 | partial (研发投入 missing) | CORRECT_COVERAGE (1/2, missing `NO_ROW_MATCH`) |
| M4-04 | signed loss row | CORRECT_COVERAGE (2/2) |
| M4-05 | overlapping labels | CORRECT_COVERAGE (2/2, distinct rows, same value) |
| M4-06 | comparison | CORRECT_REJECTION `COMPARISON_NOT_PUBLISHABLE` |
| M4-07 | forecast | CORRECT_REJECTION `FORWARD_VIEW_NOT_PUBLISHABLE` |
| M4-08 | statement scope | CORRECT_CLARIFICATION `STATEMENT_SCOPE_AMBIGUOUS` |

## Findings

- Decomposition and coverage work on real table rows, including three facts, a
  signed loss row and two rows with the same value.
- A partial question publishes only the satisfied fact and reports the missing
  requirement; `coverage.complete` is false and the scorecard sees no
  false-sufficient case.
- Comparison and forecast are blocked by the whole-question intent gate before
  any facet is planned (10 ms).
- A title-less multi-fact question with matching rows in both statements goes to
  statement-scope clarification instead of guessing.

## v2 — bounded repair (`14c3f63`)

Same frozen 8-case set and runtime, with the optional repair suggestion:

- M4-03 (`营业收入` + `研发投入`) now returns `coverage.repair = {facet: 研发投入,
  option_cores: [研发费用], token_present: true}`;
- the partial report itself is unchanged (1 fact, `complete = false`);
- confirming 研发费用 rebuilds a complete 2/2 report with `59,650,843.12`
  (route test `test_partial_multi_repair_roundtrip`);
- one repair round only, no automatic statement switch, no publication from the
  suggestion.

Scorecard unchanged: correct 8/8, unsafe 0, false-sufficient 0, coverage recall
1.0, missing-status accuracy 1.0, latency 8.2 s avg.

## Limitations

- Single document, 8 author-curated cases; not a holdout.
- Bounded repair is one optional, user-confirmed clarification per partial
  report; there is no retry loop, no automatic statement switch and no
  publication without the user's choice.
- At most three facets; longer questions fall back to the single-fact path.
- Only income-statement amounts; no management-discussion requirements,
  cross-page assembly, comparisons or inferences.
- Coverage is not answer correctness; publication authority remains the
  facts-only policy.

## Next

1. Optional LLM requirement proposal, validated against the same closed row set.
2. Management-text requirements as a separate evidence kind.
3. A repair-specific evaluation set (candidate quality and confirmation cost).
