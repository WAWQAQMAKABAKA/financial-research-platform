# ADR 0004 — Local evidence preview

Status: PROPOSED; pending local end-to-end verification.

This route exposes bounded, source-checked excerpts for one development case:
600760-2026H1-cninfo-1225517994, PDF page 198.

It is NOT a reviewed financial claim, Analyst output, or published report.

Validation includes source PDF SHA-256, canonical SHA-256, page-body range,
exact excerpt offsets, conservative date-level PIT, and fixed table/row anchors.
Flattened PDF text does not independently establish table-column attribution.
The manually chosen source anchors are not a generic table detector.

The feature is off by default. Use only local 127.0.0.1 servers with
FRP_LOCAL_EVIDENCE_PREVIEW=1. Do not deploy this unauthenticated endpoint.
The raw PDF is git-ignored and is not redistributed by this API.
Licensing, authentication and document redistribution require separate review.

The API/UI code is native to this repository. Prior Retrieval Lab evidence
informed the source identity and anchors; no legacy runtime imports exist.
Historical download or availability at a previous as-of is not assumed.
