# ADR 0012 — Serialize local FastAPI PDF-processing requests

Date: 2026-10-21
Status: PROPOSED — full regression, original-PDF re-audit and Safari acceptance pending

## Reason

During M1.7A Safari acceptance, the 600276 endpoint returned one
`CANONICAL_SHA_MISMATCH`/503 followed by success on refresh. Six subsequent
**sequential** requests and the original-PDF API audit passed. This does **not**
prove a concurrency root cause. PyMuPDF is not safe for simultaneous threaded
access in the same process, while synchronous FastAPI handlers can overlap in
worker threads. Prevention is warranted without weakening source identity.

## Scope

The four existing local PDF-related FastAPI routes share one process-local
`threading.Lock` around the entire route handler, including PDF canonicalization,
full-document table indexing and independent literal source review. Timeout
returns generic `503 SOURCE_UNAVAILABLE`, not an unchecked draft. A `finally`
block releases the lock on failures. `functools.wraps` preserves route signatures
for FastAPI. `/api/v1/health` remains unguarded.

There are no financial-value, canonical-hash, PIT, publisher or evaluator
changes. No model API calls, protected truth, trading action, or expanded
customer permissions. `research_publication=BLOCKED` remains compulsory.

## Limits and qualification

This lock protects a **single FastAPI process only**. Multiple Uvicorn workers,
separate CLI processes, background jobs and future worker pools need a separate
process-bound isolation design. It is not a PDF-thread-safety certification or
proof that the initial canonical mismatch was caused by concurrency. No code
should treat occasional hash disagreement as an acceptable retry signal.

Before committing M1.7A, run the entire backend regression and web build/lint,
repeat both original-PDF source audits, check concurrent local API requests,
and inspect both issuers' values and source-page links in Safari. Any hash
mismatch still fails closed; unexpected behavior blocks commit.
