# 0017 — Facts-only publication for one authorized disclosure

Date: 2026-11-02
Status: accepted for M1 (single vertical slice, 600760 2026H1)

## Context

Every earlier module returned `research_publication = "BLOCKED"`
unconditionally, including modules that had already verified source identity,
canonical text, cell geometry and an independent literal review. That is
fail-closed but not usable: no customer could ever see a report, and the
constant carried no information.

The corpus manifest (M0a) now declares one authorized document:
600760 中航沈飞 2026H1, source hash `d53ee98c…`, canonical hash `620d3a30…`,
207 pages. Its PDF is gitignored and provisioned locally.

## Decision

Introduce exactly one new publication state, `FACTS_ONLY`, decided by
`publication_policy.decide_publication` from the *already verified* source
draft. Approval requires, on every call:

1. the draft document id, source hash, canonical hash and source URL equal the
   corpus manifest entry;
2. PIT: `published_on + 1 day` (Asia/Shanghai) has passed;
3. the statement kind, row label and column header equal the requested
   selection, and the printed period and `单位：元 / 币种：人民币` context agree
   with the manifest reporting period;
4. the value is a plain decimal amount;
5. the claim is `OBSERVED_FACT`, has exactly one evidence id, and that id is
   bound to the observation;
6. the observation is flagged `NOT_PROVEN_FROM_TABLE_GEOMETRY` with scope
   `LITERAL_CELL_LOCATION_ONLY`;
7. one independent review returns `ADMIT` from
   `native-pdf-cell-literal-reviewer-v1` with the literal-scope rationale.

Any failure withholds the whole report and shows no numbers. Comparative,
inferential, forward-looking and management-explanation claims are never
publishable: they are listed as `NOT_PUBLISHED` capabilities.

Customer-facing label: **仅展示已核对的披露事实 · 不含财务趋势判断**.
`financial_semantic_review` stays `NOT_PERFORMED`. The report is not persisted.

## Deliberately not solved

A comparison whose entity, metric, period, unit and accounting basis all match
would still only reach `UNCERTAIN` in `semantic_gate`; the policy never admits
it. M1 therefore **fails** to publish a valid comparison on purpose. The known
invalid comparison (`COMPARISON_IDENTITY_MISMATCH:category`) remains a
rejection regression. Comparative capability is not claimed.

600276 恒瑞医药 is not part of the authorized corpus in M1: its PDF is not
provisioned locally. Its legacy workspace preview keeps returning `BLOCKED`
through a hardcoded `LEGACY_HARDCODED` entry. It is not report-capable.

## Consequences

- The report path no longer depends on a `SourceDocument(...)` literal; it
  reads the manifest. `preview.SOURCE` and `revenue_scope.SOURCE` remain for
  legacy 600276-only endpoints and are migrated in a later milestone.
- Manifest verification is a byte check, not a filename check. A provisioned
  PDF outside `data/raw/` is accepted if its bytes match.
- Reports are generated per request (~30–60 s for a 207-page document) and are
  not cached or stored.
- Access is local-development only: feature flag + 32-character shared secret +
  refusal in production builds and `FRP_ENV=production`.
