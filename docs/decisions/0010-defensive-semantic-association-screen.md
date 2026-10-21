# ADR 0010 — Defensive financial association screen (M1.6B-1)

Date: 2026-10-21
Status: PROPOSED — original-report diagnostic and repository regression pending

## Scope

Introduce a **separate, deterministic claim-association guard**, not a
financially authoritative Reviewer. It accepts structured assertion candidates
and a separately supplied source-located candidate packet. It detects explicit
mismatches in source evidence identity, source value/row/header/statement
association, candidate financial metric/category/scope/basis/period/unit, and
claims that confuse two statement scopes with period change. It screens the
**assertion structure**, irrespective of whether an Analyst labels the claim
`OBSERVED_FACT`; untyped paragraphs always remain uncertain.

The guard returns only `REJECT` or `UNCERTAIN`. It cannot return `ADMIT`, cannot
review free-form financial reasoning, and cannot change customer publication.
Matching labels are **not** proof of accounting correctness or comparability.
Source-side candidate identity fields are also not inherently trusted: the
calling pipeline must independently verify the original PDF, PIT/source hash,
original row/cell geometry and literal review. Even when all of those pass,
financial-semantic review remains `NOT_QUALIFIED` and publication `BLOCKED`.

## Known lessons and limitations

Historical Hengrui C4 compared unlike drug-category shares under an apparently
credible common denominator. This gate tests the general mismatch pattern with
synthetic figures; it must never use historical benchmark ground truth or real
reference answer values in the runtime. A relabeled source annotation could
still be wrong even if internally consistent. The source-only guard is a safety
net, **not a semantic model**. Cross-document comparisons and different literal
row labels may be legitimate; absent qualified meaning these return `UNCERTAIN`
rather than categorical rejection. Narrative causality, implicit financial
comparison in untyped prose, metric synonymy, numerator/denominator association
and independently sourced financial semantics remain future work.

## Qualification

Run synthetic regression without network. For one real-document diagnostic,
rebuild the Hengrui source draft from its original, hash-pinned 2026H1 PDF;
check that the proper single-source observation remains `UNCERTAIN` and the
false comparison of consolidated-vs-parent statement figures is `REJECT`,
regardless of an Analyst-supplied claim kind. This is not independent
real-document **semantic** approval and does not qualify a publishable report.
Do not add customer API routes, LLM calls, trading actions, or benchmark GT.
