# 0021 — Semantic review packet (development-only)

Date: 2026-11-05
Status: accepted for development use; not customer-facing

## Context

Management explanations, comparisons, inferences and forward views are withheld
until a qualified semantic review exists. The literal reviewer cannot supply it:
it verifies text and location, not meaning. Reviews must therefore pause the
pipeline, show the evidence to a named reviewer, and record an explicit verdict.

## Decision

`semantic_review` adds a review packet and an immutable review record.

**Packet.** For a management-explanation claim the first preview excerpt becomes
the claim text (verbatim source). The packet contains question, report key,
claim type, claim text, page number, excerpt, excerpt SHA-256, document identity,
a fixed six-item checklist (metric identity, period, entity, basis, evidence
support, no overreach), the allowlisted reviewers, a 900-second expiry and a
development-only marker. The packet is HMAC-signed with the local secret.

**Pause.** `POST /ask` never decides. It returns the packet with
`status = AWAITING_EXPLICIT_HUMAN_DECISION` and keeps the report withheld. No
review record and no published management claim are produced by asking.

**Decision.** `POST /api/v1/research/reviews/decide` accepts `packet_id`,
`reviewer_id`, `verdict` (ADMIT/REJECT/UNCERTAIN), the full checklist and a
rationale. It verifies the signature and expiry, the reviewer allowlist
(`FRP_SEMANTIC_REVIEWERS`, default `local-reviewer`), the exact checklist keys,
and requires all checks true for ADMIT. It records the review as JSON under
`data/private/semantic-reviews/` (0600, no overwrite; override with
`FRP_SEMANTIC_REVIEW_STORAGE`) and then applies the development gate.

**Gate.** Publication requires ADMIT, an allowlisted reviewer, all checklist
items true, and matching claim text and excerpt hash. REJECT and UNCERTAIN are
withheld with their own reasons. The result is a
`MANAGEMENT_EXPLANATION_DEVELOPMENT_REPORT` with `development_only = true` and
`independent_validation = false`; every page and record carries the same labels.

## Why these limits

- The development reviewer is `local-reviewer`. This is not independent
  validation and must never be presented as such.
- The reviewer identity is authenticated only by the local dev token plus the
  allowlist; this is not production authentication.
- The decision is explicit input. Nothing in the runtime fabricates an ADMIT.
- One claim per packet; no batch approval.

## Not implemented yet

- A qualified, independent reviewer and a customer-facing authentication model.
- An LLM pre-check (allowed later only as advisory; the verdict stays human).
- A web form for the verdict (the endpoint is the current interface).
- Multi-claim review packets.

## Consequence

A development review can publish one management-explanation claim, clearly
labelled development-only, after the reviewer inspects the packet. Without a
recorded ADMIT the claim stays withheld.
