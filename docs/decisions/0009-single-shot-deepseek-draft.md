# ADR 0009 — Explicit single-shot DeepSeek literal-claim proposal

Date: 2026-10-21
Status: PROPOSED — local offline regression and one paid original-PDF run pending

## Slice

Start with the existing **source-verified** 600276 2026H1 two-revenue-cell
prototype. After independent literal source review, a separate CLI experiment
sends only the two bounded, public disclosure cell fields to DeepSeek
`deepseek-flash` in non-thinking JSON output mode. The model returns **two
literal structured claim proposals** that must match the trusted packet field
for field. The resulting source-only sentences are generated deterministically
from accepted bindings, not unchecked model prose. This tests real API access,
model proposal parsing, evidence ID binding and token metering; it does not yet
test general analytical generation or accounting judgment.

This is a **one-shot CLI**, NOT a public endpoint or customer-facing feature.
The `--live` switch is necessary to authorize one billable request. The API key
is typed via a hidden prompt (not logged, checked in, or saved). No automatic
retries, model/provider fallback, document upload or web fetching. Explicit
client timeout and output cap. The PDF has to pass source hash, PIT, and existing
independent literal review *before* a provider request is made.

## Failure and accounting boundaries

Wrong evidence IDs, wrong source scopes, altered values, surprise schema keys,
missing token usage, malformed JSON or a truncated completion withhold **all**
model proposals. Sanitized failures never display provider response bodies.
`research_publication=BLOCKED` and `financial_semantic_review=NOT_PERFORMED`
are fixed invariants, even when a proposed literal binding matches exactly.
Neither Analyst nor Reviewer makes a CAS accounting interpretation, comparison,
or investment recommendation. No trading access or protected evaluation GT.

Usage records prompt/output/cache tokens, plus a **non-authoritative**
USD cost estimate range based on DeepSeek's published Flash off-peak/peak pricing
as of 2026-10-21 (cached input $0.003–0.006/M, uncached input $0.15–0.30/M,
output $0.60–1.20/M). Provider invoices, fees and later prices can differ.

## Qualification

Offline fake-provider tests must pass with no network or paid credits. Then
on the user's Mac run the complete original PDF and perform exactly one paid
DeepSeek request; independently inspect bindings, token report and blocked
status. Only after that may the M1.6A CLI be called locally VERIFIED and
committed. A source-cited LLM research report and finance-semantic Reviewer
remain later milestones. The runtime contains no expected real-report answers.
