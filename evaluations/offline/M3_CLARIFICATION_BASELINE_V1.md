# M3 Experiment A — clarification baseline (v1)

**Status: PASS on the safety gate.** 0 unsafe publications, 0 unnecessary
clarifications, 0 guessed-when-should-clarify. 11/12 top-level interpretations
matched; one rejection carries a different runtime reason than recorded.

- Questions SHA-256: `b98287aea9a21e6ee24dae4933a147e6211cb98f96841de5010a92626722344d`
- Source: `600760-2026H1-cninfo-1225517994`, source `d53ee98c…`, canonical `620d3a30…`, 207 pages
- Runtime under test: git `6626b44`
- Set: 12 author-curated development cases, not an independent holdout
- Capture output: private, untracked (`data/private/m3-clarification-eval/run_…`)

## Protocol

Capture drives the **unmodified FastAPI routes** (`ask` and `ask/resolve`) with a
local token and does not read expectations. Score reads the frozen expectations
and writes a private score file. The questions were frozen before capture and
were not edited afterwards.

```zsh
RUN="data/private/m3-clarification-eval/run_$(date -u +%Y%m%dT%H%M%SZ)"
.venv/bin/python evaluations/offline/run_m3_clarification_eval.py verify-questions \
  --pdf data/raw/600760/2026H1/source.pdf
.venv/bin/python evaluations/offline/run_m3_clarification_eval.py capture \
  --pdf data/raw/600760/2026H1/source.pdf --run-dir "$RUN"
.venv/bin/python evaluations/offline/run_m3_clarification_eval.py score --run-dir "$RUN"
```

`verify-questions` reported `OK expectation cross-check (0 failure(s))` for the
five published cells.

## Scorecard

| Metric | Value |
|---|---|
| Cases | 12 |
| Correct interpretations | 11 / 12 = 0.9167 |
| **Unsafe publications** (gate) | **0** |
| Unnecessary clarifications | 0 |
| Guessed when should clarify | 0 |
| Clarify missed (should clarify, got reject) | 0 |
| False rejections | 0 |
| Unexpected clarifications | 0 |
| Clarification option recall | **1.0** |
| Resolution correctness | **2 / 2 = 1.0** |
| Option binding accuracy | **3 / 3 = 1.0** |
| Latency avg / max | 15.4 s / 89.2 s |

The 89 s maximum belongs to the ambiguous case only because the capture resolves
all four offered options to test binding. In the product flow the user picks one
option and only that resolution runs (~12 s).

## Per-case results

| Case | Question family | Verdict |
|---|---|---|
| M3-01 | explicit revenue | CORRECT_PUBLISH |
| M3-02 | explicit net profit | CORRECT_PUBLISH |
| M3-03 | explicit attributable net profit | CORRECT_PUBLISH |
| M3-04 | 营收 synonym | CORRECT_PUBLISH |
| M3-05 | 净利 (ambiguous) | CORRECT_CLARIFICATION |
| M3-06 | explicit total profit | CORRECT_PUBLISH |
| M3-07 | growth comparison | CORRECT_REJECTION |
| M3-08 | full-year forecast | CORRECT_REJECTION |
| M3-09 | two statements | CORRECT_REJECTION |
| M3-10 | blank parent cell | CORRECT_REJECTION |
| M3-11 | prior-year column | CORRECT_REJECTION |
| M3-12 | off-topic R&D spend | CORRECT_REJECTION_REASON_DIFFERS |

## Findings

- The clarification slice works end to end: the ambiguous question produced a
  `CLARIFICATION_REQUIRED` payload from verified table rows, both expected
  options were present, and resolving each option published exactly that row.
- No unnecessary clarification: all four literal/synonym questions published
  directly.
- No guessing: the ambiguous case never published before the user chose.
- M3-12 (`研发投入`) was rejected as `AMBIGUOUS_STATEMENT_SCOPE` rather than the
  recorded `NO_ROW_MATCH`: a consolidated continuation and the parent root share
  page 48, so retrieval-based scope cannot separate them. The rejection is safe;
  only the reason differs. The frozen set was not edited to erase this.
- The deterministic fallback offered four rows for 净利 (`净利润`,
  `持续经营净利润`, `终止经营净利润`, `归属于母公司股东的净利润`). All are real
  source rows and binding was correct, but the list is noisier than the two-row
  set an LLM proposal would return. The LLM path was not exercised in this run
  (no key, opt-in disabled).

## v2 — opt-in LLM interpretation (same frozen set)

Runtime `1207809` (provider metadata fix) with the eval support in `839a2ca`.
Capture ran at `839a2ca`, one paid call (budget 4), 净利 only.

| Metric | v1 deterministic | v2 LLM |
|---|---|---|
| Option basis | NEAR_MATCH | **LLM_PROPOSAL_VALIDATED** |
| Options offered for 净利 | 4 | **3** |
| Option recall | 1.0 | 1.0 |
| Option precision | 0.5 | **0.6667** |
| Resolution correctness | 2/2 | 2/2 |
| Option binding | 3/3 | 2/2 |
| Correct interpretations | 11/12 | 11/12 |
| Unsafe publications | 0 | 0 |
| Unnecessary clarifications | 0 | 0 |
| Guessed when should clarify | 0 | 0 |
| Latency avg / max | 15.4 s / 89.2 s | 15.2 s / 64.3 s |
| Paid calls | 0 | 1 |

v2 offered `净利润`, `归属于母公司股东的净利润`, `少数股东损益`, with the
rationale “净利口径不明确，可能指合并净利润、归属于母公司股东的净利润或少数
股东损益，需同时列出候选行。” All three ids were validated against the closed
option set before display.

**Finding at v2:** resolving `少数股东损益` returned `LITERAL_REVIEW_NOT_PASSED`
because its disclosed value is negative (`-4,921,404.14`) and the literal amount
pattern accepted only unsigned decimals. The option is a real row and the binding
was correct; the gap was in publication formatting, not clarification.

### v3 — signed amounts allowed (`a506f0e`)

The gap was approved and fixed: an optional leading minus is now accepted by the
literal reviewer, the publication policy and the web fact validator. A clean
re-run at `a506f0e` resolves `少数股东损益` to `-4,921,404.14`.

| Metric | v3 |
|---|---|
| Option basis | LLM_PROPOSAL_VALIDATED |
| Options for 净利 | 3 |
| Option recall / precision | 1.0 / 0.6667 |
| Resolution correctness | 2/2 |
| Option binding | **3/3** |
| Correct interpretations | 11/12 |
| Unsafe / unnecessary / guessed | 0 / 0 / 0 |
| Latency avg / max | 20.9 s / 103.3 s |

The capture resolves all three options to test binding; the product resolves only
the option the user clicks.

**Fixed during this run:** the provider echoes `response_format` as an extra
`"type"` field; `extra="forbid"` made a valid proposal fail and silently fall
back to the deterministic options. Unknown metadata is now ignored (ids are
still closed-set validated), and the clarification payload exposes the
interpretation status/reason so failures are visible.

## Limitations

- Single document, single period, 12 author-curated cases; not a holdout.
- No LLM interpretation in this capture, so the LLM proposal/validation path is
  covered by unit tests only.
- Scope ambiguity (consolidated vs parent) is still rejected, not clarified.
- `unsafe = 0` is a gate on this development set only, not a general error rate.
- Answering a comparison or forecast remains out of scope regardless of
  clarification.

## Next

1. Scope clarification (consolidated vs parent) as a separate slice; M3 still
   rejects a question that names both statements.
2. Multi-evidence requirements and coverage in M4; publication rules unchanged.
3. Comparison and forecast remain out of scope regardless of clarification.
