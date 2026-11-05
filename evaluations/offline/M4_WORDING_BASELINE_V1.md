# Experiment W — wording where the conjunction split fails (v1)

**Status: measured, safe, partial improvement.** LLM planning recovered one of
the four questions the deterministic split mis-parsed; the four-metric case
stayed withheld because the plan cap is three.

- Questions SHA-256: `d07e6d785f97415dc1a74f07751e16c9d0c5c5b98f7e848cf2551a01d8319980`
- Source: `600760-2026H1-cninfo-1225517994`, source `d53ee98c…`, canonical `620d3a30…`
- Runtime: `b2b9d98` (LLM planning allowed when the conjunction split fails)
- Captures at `6217dd6`: deterministic `…_det`, LLM `…_llm`, private and untracked
- 4 author-curated development cases, not an independent holdout

## Protocol

The same question set is captured twice: once with the model disabled and once
with `--with-llm` (plan budget 8). Capture drives the unmodified ask route;
score compares published cells with the expected set and flags
under-decomposition (coverage complete but expected cells missing) and
over-answering (cells not requested).

```zsh
RUN=data/private/m4-wording-eval/run_$(date -u +%Y%m%dT%H%M%SZ)_det
.venv/bin/python evaluations/offline/run_m4_wording_eval.py capture \
  --pdf data/raw/600760/2026H1/source.pdf --run-dir "$RUN"
.venv/bin/python evaluations/offline/run_m4_wording_eval.py score --run-dir "$RUN"
# repeat with --with-llm and a second run dir
```

`verify-questions` reported `OK expectation cross-check (0 failure(s))`.

## Scorecard

| Metric | Deterministic | LLM plan |
|---|---|---|
| Cell recall | 0.5 (6/12) | **0.6667 (8/12)** |
| Complete reports | 0 | **3** |
| Single-report answers (no coverage) | 3 | 1 |
| Under-decomposition | 0 | **0** |
| Over-answer / unsafe | 0 | **0** |
| LLM-planned cases | 0 | 3 |
| Latency avg / max | 10.4 s / 11.6 s | 13.8 s / 15.3 s |

## Per-case results

| Case | Wording | Deterministic | LLM plan |
|---|---|---|---|
| W-01 | 营业收入是多少？净利润又是多少？ | 2 facts in one single report, no coverage | COMPLETE (2/2) |
| W-02 | three separate question sentences | 3 facts in one single report, no coverage | COMPLETE (3/3) |
| W-03 | 营业收入是多少？净利润和营业成本呢？ | partial: 1 fact, ambiguous first facet | COMPLETE (3/3) |
| W-04 | four metrics in one question | withheld `TOO_MANY_ROW_MATCHES` | withheld `TOO_MANY_ROW_MATCHES` |

## Findings

- W-01/W-02 were already answered by the single-fact path because the whole
  question contains several row labels; the LLM plan adds explicit coverage
  rather than new facts.
- W-03 is the real gain: the conjunction split produced a facet containing two
  metrics, which stayed ambiguous; the model proposed three clean facets and the
  report completed 3/3.
- W-04 stayed withheld. The model likely proposed four facets, which is rejected
  by the 3-facet validation, so the route fell back to the single path and hit
  `TOO_MANY_ROW_MATCHES`. This is safe (no metric silently dropped) but the
  question remains unanswered.
- No under-decomposition and no over-answer appeared in either run.

## v2 — six-requirement ceiling (`ab49889`)

The set now has five cases (`49f7b892…`): the four wording cases plus a
seven-metric question that must be rejected with its count. The plan and the
single-path row match both accept up to six requirements.

**Deterministic capture (measured):**

| Metric | v2 deterministic |
|---|---|
| Cell recall | **0.8333 (10/12)** |
| Complete reports | 1 (W-04, four metrics) |
| Single-report answers | 2 (W-01, W-02) |
| Under-decomposition | 0 |
| Over-answer / unsafe | 0 |
| Over-limit correctly rejected | **1** (W-05, detected 7) |
| Latency avg / max | 41.3 s / 56.9 s (host load up to 22) |

| Case | Result |
|---|---|
| W-01 | 2 facts in one single report (no coverage) |
| W-02 | 3 facts in one single report (no coverage) |
| W-03 | partial 1 fact, deterministic split still mis-parses the pair |
| W-04 | **COMPLETE 4/4** — dynamic ceiling admits the fourth metric |
| W-05 | **OVER_LIMIT_REJECTED** — `TOO_MANY_REQUIREMENTS`, detected 7, max 6 |

**LLM capture v2 (measured at `bc852ef`, after the host recovered):**

| Metric | Deterministic | LLM plan |
|---|---|---|
| Cell recall | 0.8333 (10/12) | **1.0 (12/12)** |
| Complete reports | 1 | **4** |
| Single-report answers | 2 | 0 |
| Under-decomposition | 0 | **0** |
| Over-answer / unsafe | 0 | **0** |
| Over-limit correctly rejected | 1 | 1 |
| LLM-planned cases | 0 | 4 |
| Latency avg / max | 41.3 s / 56.9 s* | 12.1 s / 13.5 s |

\*The deterministic capture ran while the host load was 10–22 and its latency is
not comparable.

| Case | Deterministic | LLM plan |
|---|---|---|
| W-01 | 2 facts single report | COMPLETE 2/2 |
| W-02 | 3 facts single report | COMPLETE 3/3 |
| W-03 | partial 1 fact | COMPLETE 3/3 |
| W-04 | COMPLETE 4/4 | COMPLETE 4/4 |
| W-05 | rejected, detected 7 | rejected, detected 7 |

With the six-requirement ceiling the model can answer all four requested metrics
(W-04) and still rejects seven with the count (W-05). No under-decomposition and
no over-answer in either run.

## Limitations

- Four cases, one document; not a holdout.
- The 3-facet cap limits questions with four or more metrics. Raising it is a
  product decision, not a bug fix.
- LLM planning adds one paid call and ~3 s average latency.
- Coverage completeness counts planned facets, not every metric a question might
  imply; W-04 shows why the cap must stay explicit.

## Next

1. Management-text requirements as a separate evidence kind.
2. Unseen-document validation once a second document is authorized.
3. Re-run the full suite on a loaded host to confirm stability, not behavior.
