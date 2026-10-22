# ADR 0016 — M1.9A offline financial-semantic development baseline

Date: 2026-10-22
Status: PROPOSED — requires Mac full regression, source audit and baseline output review.

## Narrow scope

Freeze production Analyst and Reviewer at M1.8B commit
`68112420ff674225efffda8f06958fb826d82f80`. Add an isolated,
network-free **development-only evaluation harness** under `evaluations/offline/`.
No production route, agent, provider call, prompt, model, or claim contract
changes. No customer release; research publication remains `BLOCKED`.

## Evidence and separation

The labelled development cases use wholly synthetic numbers, issuer, claims,
reference labels and reasons. Reference labels are not copied into the
runtime source tree. This is *not* benchmark GT, an OOS qualification, or an
independently reviewed accounting dataset. The evaluator calls the existing
`semantic_gate.screen_financial_association` and `SourceDocument.require_available`
unchanged; it does not patch them or skip rejected cases.

A distinct optional read-only real-PDF diagnostic reuses the pinned Hengrui
2026H1 original disclosure to verify the two literal income-statement cells,
management passage, three provenance IDs, PIT cutoff and conservative screening
outcomes. This was the **development report**; thus it cannot measure unseen
real-document semantic correctness or independent financial meaning.

## Baseline measurement and expected shortfalls

Output case-level expected/actual/reason/trace and aggregate counts: exact
synthetic label matches, expected REJECT recall, missed explicit contradictions
that return UNCERTAIN, false rejects of expected uncertain cases, unqualified
admissions, abstention rate, PIT checks, and source trace checks. Narrative
cases `S13` (wrong share denominator) and `S14` (wrong growth attribution)
should expose the current gate's inability to parse financial meaning in a
free-form paragraph. Do not call UNCERTAIN on these an accepted claim:
financial-semantic approval and publication remain unavailable.

`UNCERTAIN` cases include facts, unverified causal narratives, and cross-document
comparisons. Incorrect narrative meaning is not safely solved by rejecting
all inference, nor by assuming the source candidate's model-supplied labels
constitute ground truth.

## Acceptance and future work

1. Mac is clean `main` at M1.8B baseline; pull `--ff-only` before installing.
2. The offline corpus/runner does not appear in production code imports.
3. Baseline exposes unresolved cases without changing reference labels.
4. Full existing 210-test backend regression + new isolated evaluator tests,
   Next.js TypeScript build and lint pass.
5. Original pinned PDF audit passes with existing on-disk report; no provider
   call and no real-document reference figures embedded in the corpus.
6. Commit only the new offline evaluation and this ADR after verification.

M1.9B must target observed misses with a source-independent, constrained
financial-semantic check, then undergo a separate OOS qualification. Do not
add benchmark ground truth to product runtime or revise tests to conceal a gap.
