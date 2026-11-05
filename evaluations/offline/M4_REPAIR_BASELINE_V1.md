# Experiment R — bounded-repair baseline (v1)

**Status: PASS.** 2/2 repair candidates found and confirmed, 2/2 no-candidate
partials stayed clean, 2/2 complete controls unaffected, 0 unsafe publications.

- Questions SHA-256: `087474ed446ee47bca6dbcb37c0d939be6f250ffe52927545a09dd3b0357717b`
- Source: `600760-2026H1-cninfo-1225517994`, source `d53ee98c…`, canonical `620d3a30…`, 207 pages
- Runtime: `d630576` (repair implementation `14c3f63`, unchanged here)
- Capture at `7fb7294`, private and untracked
- 6 author-curated development cases, not an independent holdout

## Protocol

Capture drives the unmodified `ask` route. When a partial report carries a
repair suggestion, capture resolves every offered option (cap 3) through
`ask/resolve` and records the rebuilt report. Score checks candidate presence and
order, confirmation outcome, clean partials and unexpected facts.

```zsh
RUN="data/private/m4-repair-eval/run_$(date -u +%Y%m%dT%H%M%SZ)"
.venv/bin/python evaluations/offline/run_m4_repair_eval.py verify-questions \
  --pdf data/raw/600760/2026H1/source.pdf
.venv/bin/python evaluations/offline/run_m4_repair_eval.py capture \
  --pdf data/raw/600760/2026H1/source.pdf --run-dir "$RUN"
.venv/bin/python evaluations/offline/run_m4_repair_eval.py score --run-dir "$RUN"
```

`verify-questions` reported `OK expectation cross-check (0 failure(s))`.

## Scorecard

| Metric | Value |
|---|---|
| Cases | 6 |
| Repair cases | 2 |
| Repair offered | **2/2** |
| Candidate recall (target present) | **1.0** |
| Candidate top-1 hit | **2/2** |
| Confirmation success | **2/2** |
| Correct partial without candidate | **2/2** |
| Correct complete controls | **2/2** |
| Unexpected repair offers | **0** |
| **Unsafe publications** | **0** |
| Latency avg / max (ask + resolve) | 19.8 s / 33.2 s |

## Per-case results

| Case | Facet | Result |
|---|---|---|
| R-01 | 研发投入 | REPAIR_CONFIRMED — offered 研发费用, rebuilt 2/2 with 59,650,843.12 |
| R-02 | 研发支出 | REPAIR_CONFIRMED — same candidate, rebuilt 2/2 |
| R-03 | 研究费用 | CORRECT_PARTIAL — no candidate, no repair offered |
| R-04 | 员工人数 | CORRECT_PARTIAL — no candidate, no repair offered |
| R-05 | 其中：利息费用 | CORRECT_COMPLETE — real row, no repair needed |
| R-06 | 五、净利润 | CORRECT_COMPLETE — control |

## Findings

- The lexical candidate exactly matched the intended row in both repair cases,
  and it was the first option.
- Confirming the candidate rebuilt a complete report; the already-verified fact
  was preserved and no extra fact appeared.
- Facets with no lexical candidate (研究费用, 员工人数) stayed partial and did
  **not** receive a speculative option — `unexpected_repair_offers = 0`.
- Complete questions were unaffected; no suggestion is shown when coverage is
  complete.
- Repair never calls the model; the paid path plays no role here.

## v2 — repair under the LLM plan path (`86085f5`)

Same frozen 6-case set, `--with-llm` (plan budget 8). All six cases used
`LLM_PROPOSAL_VALIDATED` and the proposed facets matched the questions:

| Metric | v1 deterministic | v2 LLM plan |
|---|---|---|
| LLM-planned cases | 0 | **6/6** |
| Repair offered | 2/2 | 2/2 |
| Candidate recall / top-1 | 1.0 / 2/2 | 1.0 / 2/2 |
| Confirmation success | 2/2 | 2/2 |
| Clean partials without candidate | 2/2 | 2/2 |
| Complete controls | 2/2 | 2/2 |
| Unexpected repair offers | 0 | 0 |
| Unsafe publications | 0 | 0 |
| Latency avg / max | 19.8 s / 33.2 s | 18.1 s / 29.0 s |

The repair candidates are produced deterministically from the same verified
rows, so the LLM plan does not change candidate quality here. What changes is
the recorded interpretation (`coverage.plan_source`) and one paid call per
multi-fact question. The value of LLM planning would appear on question wording
the conjunction split mis-parses, which this set does not contain.

## Limitations

- Two repair cases, one document; not a holdout.
- Candidates are lexical near-matches confirmed by the user, not semantic
  equivalence. `研发投入 → 研发费用` is the user's decision.
- Only the first missing facet is offered; at most one repair round.
- Latency includes resolving the candidate (one extra report build).
- Coverage and repair do not change the publication policy.

## Next

1. Management-text requirements as a separate evidence kind.
2. Unseen-document validation once a second document is authorized.
3. A wording set where the conjunction split fails, to measure LLM planning
   value rather than parity.
