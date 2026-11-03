# M2a Track A — 600760 cell-level baseline (v1)

**Status: v1 FAIL on the safety gate; v2 (P0/P1/P2) 0 unsafe, 0 wrong-cell.**
v1 published a fact for two expected-rejection questions and one extra row.
The frozen set was not changed between v1 and v2.

- Questions SHA-256: `b7e2db373d021355e107ca335ce17207ecb3c75703c67bda95ec9db5f645e727`
- Source: `600760-2026H1-cninfo-1225517994`, source `d53ee98c…`, canonical `620d3a30…`, 207 pages
- Runtime: v1 `e558dc8`; v2 `721cc58` (P0/P1/P2), captured at `3bd8c92`
- Set: 15 author-curated cases, development only, **not an independent holdout**
- Captured trace and score: private, untracked, outside tracked files

## Checkpoint 1 — freeze expectations (reproduce)

**Purpose:** prove the expected cells come from the original PDF, not from the
selector, and freeze the question set by hash before any capture.

**Expected output:** source/canonical identity OK; one `OK` line per published
expectation; `OK expectation cross-check (0 failure(s))`; the SHA-256 above.

**Commands:**

```zsh
cd /Users/wywaq/projects/financial-research-platform

git rev-parse --abbrev-ref HEAD
git rev-parse HEAD
git status --short
git pull --ff-only

.venv/bin/python scripts/verify_corpus.py --canonical

shasum -a 256 evaluations/offline/m2a_600760_questions_dev_v1.json

.venv/bin/python evaluations/offline/run_m2a_cell_eval.py verify-questions \
  --questions evaluations/offline/m2a_600760_questions_dev_v1.json \
  --pdf data/raw/600760/2026H1/source.pdf
```

**Verification:** the hash must equal the value above; `verify-questions` must
report `0 failure(s)`; `scripts/verify_corpus.py --canonical` must print
`OK  600760-2026H1`.

**Stop condition:** any hash mismatch, any `FAIL:` line, or a dirty runtime file
under `services/api/` — stop, do not capture.

## Checkpoint 2 — label-blind capture

`capture` loads only `case_id`, `family` and `question`; expectations are stripped
before the runtime is called. The unmodified `build_report_from_question` is used.

```zsh
RUN="data/private/m2a-eval/run_$(date -u +%Y%m%dT%H%M%SZ)"
.venv/bin/python evaluations/offline/run_m2a_cell_eval.py capture \
  --questions evaluations/offline/m2a_600760_questions_dev_v1.json \
  --pdf data/raw/600760/2026H1/source.pdf \
  --run-dir "$RUN"
```

`~/.cache` is not writable under the current sandbox, so the trace is written to
the gitignored `data/private/` area. Each run uses a new directory; an existing
run directory or output file is refused so prior evidence is never overwritten.

## Checkpoint 3 — score

```zsh
.venv/bin/python evaluations/offline/run_m2a_cell_eval.py score \
  --questions evaluations/offline/m2a_600760_questions_dev_v1.json \
  --run-dir "$RUN"
```

## Baseline scorecard

| Metric | Value |
|---|---|
| Cases | 15 (8 expected publish, 7 expected reject) |
| **Unsafe publications** (gate) | **2** |
| **Wrong-cell publications** (gate) | **1** |
| Exact cell matches | 6 / 8 = 0.75 |
| Correct rejections | 5 / 7 = 0.7143 |
| False rejections | 1 / 8 = 0.125 |
| Exact runtime-reason accuracy | 4 / 5 = 0.8 |
| Rejection category accuracy | 3 / 5 = 0.6 |
| Citation page accuracy | 1.0 |
| Retrieval page recall @1 / @3 / @5 | 0.625 / 0.75 / 0.75 |
| Latency avg / max | 12.4 s / 16.9 s |

Zero unsafe publication is a gate **on this development set only**, not a general
error rate.

## Per-case attribution

| Case | Verdict | Attribution |
|---|---|---|
| M2A-01 revenue | EXACT | Explicit statement scope; literal sub-row selected. |
| M2A-02 operating cost | EXACT | Did not confuse 营业成本 with 营业总成本. |
| M2A-03 total operating cost | EXACT | Distinct row core matched. |
| M2A-04 net profit | EXACT | Generic row matched; continuation page handled. |
| M2A-05 total profit | EXACT | Continuation page and parenthetical annotation handled. |
| M2A-06 attributable net profit | **WRONG_CELL** | Question contains both 归母净利润 and 净利润; both rows matched and were published. Over-answering: the selector needs most-specific-match precedence. |
| M2A-07 parent revenue blank | CORRECT | Blank cell is not zero. |
| M2A-08 prior-year question | CORRECT | Out-of-period guard fired before extraction. |
| M2A-09 no statement named | EXACT | Retrieval page priority selected consolidated and disclosed the basis. |
| M2A-10 营收 synonym | **FALSE_REJECTION** | No alias mapping; literal core match failed. Improvement target. |
| M2A-11 净利 synonym | CORRECT (reason differs) | Runtime returned `NO_ROW_MATCH`; the intended category was ambiguous metric identity. Safe, but the reason is not yet semantic. |
| M2A-12 growth comparison | **UNSAFE** | The comparison question contains 营业收入; the literal row matched and the current-period value was published. Needs an intent/assertion gate before selection. |
| M2A-13 full-year forecast | **UNSAFE** | Same calendar year passes the period guard; the full-year forecast wording is not recognized. Needs a forward-view guard. |
| M2A-14 two statements | CORRECT | `AMBIGUOUS_STATEMENT_SCOPE`; no guess. |
| M2A-15 R&D spend | CORRECT (reason differs) | Expected `NO_SOURCE_ROW`; actual `AMBIGUOUS_STATEMENT_SCOPE` because a consolidated continuation and the parent root share page 48. Expectation nuance, frozen set unchanged. |

## v2 — after P0 / P1 / P2

Runtime `721cc58`. Same frozen set, same SHA-256, same 15 cases, captured at
`3bd8c92` with a clean tree.

| Metric | v1 | v2 |
|---|---|---|
| Unsafe publications (gate) | 2 | **0** |
| Wrong-cell publications (gate) | 1 | **0** |
| Exact cell matches | 6/8 = 0.75 | **8/8 = 1.0** |
| Correct rejections | 5/7 = 0.7143 | **7/7 = 1.0** |
| False rejections | 1/8 = 0.125 | **0** |
| Exact reason accuracy | 4/5 = 0.8 | 4/5 = 0.8 |
| Rejection category accuracy | 3/5 = 0.6 | 5/7 = 0.7143 |
| Citation page accuracy | 1.0 | 1.0 |
| Retrieval page recall @1/@3/@5 | 0.625/0.75/0.75 | 0.625/0.75/0.75 |
| Latency avg / max | 12.4 s / 16.9 s | 9.0 s / 12.2 s |

What changed:

- **P0 (intent gate, `intent_gate.py`)**: M2A-12 and M2A-13 are now withheld in
  3 ms, before retrieval, with `COMPARISON_NOT_PUBLISHABLE` and
  `FORWARD_VIEW_NOT_PUBLISHABLE`. A literal token match inside a comparison or
  forecast can no longer publish the current-period value.
- **P1 (specificity)**: M2A-06 publishes only the attributable row;
  `specificity_dropped` records `["净利润"]`. A generic "净利润" question still
  does not reach the attributable row.
- **P2 (audited synonyms)**: M2A-10 ("营收") now selects 其中：营业收入 and
  records `synonyms_applied`; "净利" is not mapped and still withholds.

Remaining gaps, reported rather than hidden:

- M2A-11 correct rejection carries `NO_ROW_MATCH`, not a metric-identity reason;
  category accuracy counts it as a mismatch.
- M2A-15 remains `AMBIGUOUS_STATEMENT_SCOPE` versus the recorded
  `NO_SOURCE_ROW` expectation: a consolidated continuation and the parent root
  share page 48. The frozen prefix is unchanged.
- Recall@1 is still 0.625; retrieval ranking is a diagnostic input only and was
  not changed in this round.
- Zero unsafe publication is a gate on this development set only, not a general
  error rate.

## What this does and does not show

- The publication gate itself held: no unsafe publication came from the policy —
  all three failures happen **before** publication, in question understanding and
  row selection.
- Literal row selection is reliable for explicit, unambiguous questions (6/6).
- The weaknesses are exactly three: comparison/forecast intent, most-specific-row
  precedence, and synonym/metric normalization.
- Recall@1 of 0.625 means the expected page is often not the top retrieved chunk;
  page-level retrieval is a diagnostic, not a publication input.

## Next (not executed here)

1. Metric-identity reason for ambiguous aliases such as 净利, so the rejection
   category matches the financial semantics rather than `NO_ROW_MATCH`.
2. Retrieval ranking (recall@1 0.625): candidate quality, not publication.
3. A true unseen set on a provisioned, independently verified second document.
4. Re-run the **same frozen set** after every change and compare against v2.
   Do not edit the frozen set to make a case pass.
