# M130-B4A: A-share common-question development pilot

**Status:** PROPOSED until installed, tests and three original-PDF captures verified. This
pilot is not an independent holdout and produces no financial answer GT.

## Boundary

- Three source-qualified **2026 H1 full reports**: 600276 (SSE), 600519 (SSE),
  000651 (SZSE). The source URL, PDF SHA-256, canonical SHA-256, filing date and
  number of PDF pages are pinned in the question manifest.
- Thirty **author-curated**, common Chinese research questions (ten per report).
  These questions are *not* claims about the availability of source evidence.
  Source documents have already been inspected in M130-A/B1/B2; none is an
  independent untouched holdout. Variants, hard cases and future questions are
  included but answerability is deliberately **unlabeled**.
- Questions include consolidated versus parent statement scope, recognized
  revenue versus potential deal value, cash flow versus profit, product/channel
  segmentation, and unsupported future-certainty prompts. No financial answers
  are coded or asserted.
- The offline retrieval capture imports the **unchanged production retrieval
  interface** only. Original PDFs remain in the user's private cache and must
  match the exact original and canonical hashes. PIT is checked for each report.
- No network, LLM, GT, trading state, production source routing change, report
  storage, claim approval, or publication. This is *retrieval diagnostics*, not
  a customer-facing multi-issuer research report.

## Capture and evidence review

Run the offline utility from the repository root with the private source cache
from M130-B1 present. First generate the review form **without looking at the
retrieval trace**. The reviewer should inspect the official PDF itself and fill
in `answerability`, **1-based PDF page numbers** (not printed page labels),
`evidence_note`, `reviewer`, and `reviewed_at`. Use semicolon-separated page
numbers for multiple pages. Annotate the **minimal complete set** of pages
needed to answer the literal question, including both pages for comparisons.

Allowed reviewer answerability labels for the next checkpoint (M130-B4B):
`ANSWERABLE`, `PARTIALLY_ANSWERABLE`, `NOT_SUPPORTED_IN_REPORT`, `AMBIGUOUS`,
`REVIEW_PENDING`. Do not infer `NOT_SUPPORTED_IN_REPORT` from a failed keyword
search; check likely sections and tables in the full report. Distinguish
reporting-period, consolidated/parent company, business-segment, revenue
recognition, units, and denominator ambiguities explicitly.

The blank annotation form contains **no retrieved candidate pages**; the
retrieval trace separately records source-bound candidates for later scoring.
Do not score the form until the annotations are reviewed, audited for page
count and source SHA, and frozen. Human-annotated development labels are not
an independent holdout or a source of runtime truth.

## What to measure after annotation

- Report and query coverage, percent annotated and answerability distribution.
- **Distinct PDF-source-page recall@1/@3/@5** only for cases with reviewed
  relevant pages; count unique pages, not repeated chunks. Page-level recall
  does not prove support for a claim, financial answer accuracy or sufficiency.
- First relevant rank, ranking misses, table flattening/geometry problems,
  query ambiguity, unsupported requests, and span-provenance failures.
- Compare later against lexical baseline on **identical frozen questions**.
  Do not tune on a separate untouched A-share holdout, and never load labels
  into runtime or prompts.

## Gates

1. Verified repo branch/HEAD, clean status, `git pull --ff-only`, then a
   guarded installation of these four new evaluation-only files.
2. Python offline unit tests and unchanged backend regression suite pass.
3. Label-blind capture for **all 30** cases with source/hash/PIT/offset checks.
4. Annotation review: manual, source-first, no retroactive editing to match hits.
5. Separate scorer design and results only after reviewed references exist.

**Not measured in B4A:** source-page recall, answer truthfulness, completeness,
claim citations, financial-semantic correctness, independent holdout quality.
