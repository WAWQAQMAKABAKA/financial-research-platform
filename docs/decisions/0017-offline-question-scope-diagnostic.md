# ADR 0017 — M121A offline question-routing scope diagnostic

Date: 2026-10-25
Status: DRAFT — isolated branch, Mac verification pending

## Problem

M120 supports exactly two question-to-original-source presentations for
600276 2026H1: consolidated revenue LOOKUP and management-attributed
innovative-drug share of drug sales RATIO. This is not general question
understanding. A keyword prefilter may admit a question containing the right
words plus a second unsupported task (multi-year comparison, extra metric, or
verification), then display a narrow literal answer as if it addressed the
whole question.

The 40-item author-designed question-understanding development corpus is
broad. Static reproduction of the current router admitted Q01 and Q03 only;
that 2/40 figure is **scope eligibility**, not model understanding accuracy,
and is not a quality score. The exact Python baseline requires Mac execution.

## Decision for M121A

Add a **purely offline, read-only development diagnostic** under
`evaluations/offline/`, with deliberately supported and unsupported
examples. Evaluate the production prefilter as-is and report separately:

- `false_admit_ids`: author-designed unsupported multi-part or semantic
  questions nonetheless routed to an existing narrow answer.
- `false_withhold_ids`: supported single-intent questions refused.
- `wrong_route_ids`: eligible question sent to the wrong source kind.
- case count and breakdown by family.

The runner imports the current prefilter but the runtime never imports the
runner or its labels. Neither model, PDF, network, source answer, broker,
research report, nor publication is invoked. No existing application
routing, tests, prompts, or finance interpretation are changed.

Case labels are development design decisions, not independently reviewed
financial semantics or held-out ground truth. Source retrieval recall,
citation validity, LLM intent accuracy, and accounting correctness remain
`NOT_MEASURED`. Publication remains `BLOCKED`.

## M121B design gate, not implemented here

Decouple (1) open-ended question understanding, (2) structured task
decomposition, (3) source availability and PIT, and (4) per-claim source-bound
answer coverage. A single supported subquestion may be shown only as
**partial** with the unmet subquestions explicit, never as a complete answer.
Missing evidence must yield a visible refusal/uncertainty, not a fabricated
metric or a silent substitution of company consolidated revenue for drug
sales. Re-evaluate category-level false admissions and false refusals across
at least two issuers and multiple original documents before broadening the
customer-facing route. Do not introduce additional agent orchestration.

## Mac acceptance before this branch can be merged

1. Confirm local HEAD/branch/status without altering the M120 working tree.
2. Execute the diagnostic with the repo's pinned Python environment:

   ```sh
   PYTHONPATH="$PWD/services/api" .venv/bin/python evaluations/offline/run_question_scope_diagnostic.py
   PYTHONPATH="$PWD/services/api:$PWD/evaluations/offline" .venv/bin/python -m unittest discover -s evaluations/offline -p 'test_*.py' -v
   PYTHONPATH="$PWD/services/api" .venv/bin/python -m pytest -q services/api/tests
   ```

3. Review exact case-level false admissions; do not alter labels merely to
   improve a score. Confirm the read-only diagnostic does not call DeepSeek
   or read the original PDF.
4. Verify no source PDF, secret, browser, or financial ledger data committed.
5. M121A diagnostics do not replace two-issuer native-PDF source verification
   or Safari acceptance when M121B changes customer behavior.

Only Mich can approve engineering integration; no Jason financial ruling,
trading permission, or financial-semantic approval is implied.
