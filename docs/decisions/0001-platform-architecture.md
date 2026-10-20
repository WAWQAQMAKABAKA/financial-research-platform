# ADR 0001 — Platform architecture

Date: 2026-10-19
Decision: ACCEPTED
Implementation: IN PROGRESS

## Structure

- Next.js / TypeScript customer UI.
- Modular FastAPI backend with versioned routes.
- Independently owned research modules.
- Shared evidence, provenance, PIT, and citation infrastructure.
- Explicit external API adapters.
- Protected evaluation is strictly offline.

## First research module

Financial Report Analyst:
one authorized disclosure, one question,
bounded Analyst and independent Reviewer,
source-traceable customer report,
fail-closed publication.

## Isolation

Quant Desk, Retrieval Lab, and Financial
Research Workflow are read-only references.

Code reuse requires source provenance
and authorization verification.

No legacy runtime imports, hidden file-sharing,
trading-state access, or protected GT in runtime.

## Initial implementation

The health endpoint and research status page
are infrastructure only, not research capability.
