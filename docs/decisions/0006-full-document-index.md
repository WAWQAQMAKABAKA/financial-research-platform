# ADR 0006 — Candidate-only full-document PDF structure index

Date: 2026-10-20
Status: PROPOSED — pending independent 600760 full-document audit and external-company qualification

## Scope

The native `app.evidence.document_index.index_document(source, pdf_path, as_of)`
uses the existing PyMuPDF dependency to process **all pages** of an authorized
source-verified PDF. Its output includes document/source/canonical hashes,
per-page table candidates, per-cell text/geometry (including blanks), isolated
statement-heading candidates, and potential continuation relationships.

No issuer-specific numeric answer, page number, expected column label, or
benchmark annotation enters the module. Section-name vocabulary is reusable,
versioned Chinese accounting terminology. Page numbers are discovered outputs.

A new section heading halfway down a page is a **positional boundary**: a
preceding table can remain a previous-statement continuation candidate while
a later table begins a new statement candidate.

## Hard limits

* All table/section assignments are **REVIEW_REQUIRED** candidates, never
  certified reporting-entity scope, period associations, or financial facts.
* Cross-page geometry is insufficient to prove section continuity; there is
  **no automatic semantic merge**. Native text is not an OCR/scanned-PDF solution.
* A cell with missing/empty extracted text is `BLANK_OR_UNEXTRACTED`, not zero.
* A document-wide scan can miss unruled tables, blended layouts, or captions.
  Missing or ambiguous structural coverage does not authorize publication.
* `SourceDocument.require_available(as_of)` and source/canonical SHA-256 are
  mandatory; the current conservative date-level PIT does not demonstrate
  historical possession of the source document.
* No API route, client UI, Analyst/Reviewer authority, or public release is
  added. `research_publication` is always `BLOCKED`.
* The application runtime does **not** have access to the offline visual
  references or protected benchmark ground truth.

## Qualification

First inspect the 600760 2026H1 full-document index using a *separate local
read-only audit* of pages 46–48 and 198. Then evaluate unchanged extraction
code on independently selected Chinese listed-company filings with differing
layout, accounting scope, and company-specific financial statement organization.
No such external qualification has yet been completed.

## Provenance

Fresh native implementation using PyMuPDF `find_tables` and text-line geometry.
Informed by earlier exploratory scripts run outside this repository; no
copied legacy-repo source, imports, or cross-repository file sharing.
Pin: PyMuPDF 1.28.2 as already listed in `services/api/requirements.in`.
Licensing, redistribution, and customer deployment still require review.
