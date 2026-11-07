# M5.1 — Semantic review milestone (development-only)

Status: frozen for review before any customer-facing use
Runtime: `04b560c` (2026-11-07)
Backend tests: 648 passed · Web type-check: `tsc --noEmit` passed

This milestone closes the loop from a management-explanation question to a
source-bound, human-reviewed, development-only report. It does **not** authorize
customer-facing publication.

## What exists

### 1. Management evidence preview (M5 v1)

`build_management_report` locates the management discussion section from page
headings (`管理层讨论与分析` up to the next `第…节`), selects lines that carry both
a question metric and an explanation cue, and returns at most three page-text
excerpts. Publication stays `REPORT_WITHHELD` with
`MANAGEMENT_EXPLANATION_REQUIRES_SEMANTIC_REVIEW` and
`semantic_review = NOT_PERFORMED`.

Selection rules: explanation stopwords and generic time/company grams are removed
from question metrics; the first line of a window must itself carry a metric and
a cue; continuation lines are joined only when the first line lacks ending
punctuation and the next line is prose; checkbox/number-only lines are skipped;
marker phrases (`变动原因`, `主要是`, `主要系`, `原因说明`) rank higher.

### 2. Review packet

For the top preview excerpt the packet contains:

- claim type (`MANAGEMENT_EXPLANATION`), claim text (verbatim, complete sentence);
- page number, excerpt, excerpt SHA-256;
- the complete page text as `context`, context SHA-256;
- document identity (`document_id`, `source_sha256`, `canonical_sha256`);
- the six-item checklist;
- allowlisted reviewers, expiry (900 s default, `FRP_SEMANTIC_REVIEW_TTL` override);
- `development_only = true`, `independent_validation = false`.

The packet is HMAC-signed with the local secret. Asking never records a decision.

### 3. Explicit decision

`POST /api/v1/research/reviews/decide` (or the web form) takes `packet_id`,
`reviewer_id`, verdict (`ADMIT`/`REJECT`/`UNCERTAIN`), the six booleans, optional
per-item notes and a rationale. It verifies the signature and expiry, the
reviewer allowlist (`FRP_SEMANTIC_REVIEWERS`, default `local-reviewer`), the exact
checklist keys, and requires all six true for `ADMIT`.

The review record is written as immutable JSON under
`data/private/semantic-reviews/` (0600, no overwrite, gitignored; override with
`FRP_SEMANTIC_REVIEW_STORAGE`). It stores the claim, excerpt, context, hashes,
page, document identity, checklist, per-item notes, rationale and timestamp.

### 4. Reuse

Before returning a packet, the ask path looks up stored reviews by claim text,
excerpt hash, context hash, page, document id, source hash and canonical hash.
An allowlisted `ADMIT` with all checks true returns the development report with
the stored review attached. `REJECT`, `UNCERTAIN`, a non-allowlisted reviewer or
any changed content returns a fresh packet. The newest matching record wins.

- management-only question → `MANAGEMENT_EXPLANATION_DEVELOPMENT_REPORT`
- mixed fact + explanation → `FACTS_WITH_MANAGEMENT_CLAIM_REPORT` (fact published
  through the normal policy, reviewed claim attached)

### 5. Web

The review packet renders a plain HTML form (six checkboxes + per-item notes,
verdict, rationale). It posts to a server-side Next route that forwards to the
API with the server-side local token; the token never reaches the browser.
Submission errors are visible; success redirects back to the question, where the
stored `ADMIT` is reused. The page renders the development report and the mixed
reviewed claim with `development_only` / `not independently validated` labels.

## First real review

| Field | Value |
|---|---|
| review_id | `4ecff5801ee863fc983d6a81c4f6779c` |
| reviewer | `local-reviewer` |
| verdict | `ADMIT` |
| recorded_at | 2026-11-07T08:24:28Z |
| claim | 营业收入变动原因说明：主要是受产品结构调整及部分配套成品交付节奏等因素影响，交付呈现阶段性偏差。 |
| page | 10 |
| checklist | all six true, with per-item notes |
| storage | `data/private/semantic-reviews/4ecff58….json` |

The reviewer explicitly supplied each check, the verdict and the rationale in
conversation. The platform did not infer any of them.

## Invariants

- No auto-ADMIT, no LLM verdict, no batch approval.
- A decision binds to the exact content hashes; changed content needs a new
  packet and a new decision.
- Published facts still pass `publication_policy`; the management claim passes
  the development-only semantic gate.
- Every report and record carries `development_only` and
  `independent_validation = false`.
- No ground truth, evaluation label or expected answer enters runtime.

## Verification performed

- Backend: 648 passed.
- Web: `tsc --noEmit` passed; live dev-server check showed the packet form on an
  unadmitted claim and the development report on the admitted revenue claim.
- No decision was submitted during verification; the review count stayed one.
- The route test that expected a preview is isolated from the real review storage
  so it does not accidentally reuse the recorded decision.

## Known limitations

- `local-reviewer` is not independent; this is not customer-facing validation.
- Local dev token only; no production authentication or authorization.
- One claim per packet; no batch review.
- The claim is a verbatim excerpt, not a synthesized answer or causal analysis.
- REJECT/UNCERTAIN feedback in the page is minimal (the packet returns).
- Review storage is file-based with no locking or rotation.
- Mixed reuse covers the management claim only; facts are unchanged.
- Only `600760-2026H1`; no unseen-document validation.

## How to run

```zsh
# backend
cd services/api
FRP_LOCAL_FACTS_REPORT=1 \
FRP_LOCAL_LLM_ACCESS_TOKEN=<local-token> \
FRP_LOCAL_SOURCE_PDF_600760=data/raw/600760/2026H1/source.pdf \
../../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000

# web
cd apps/web
RESEARCH_API_BASE_URL=http://127.0.0.1:8000 \
FRP_LOCAL_FACTS_REPORT=1 \
FRP_LOCAL_LLM_ACCESS_TOKEN=<local-token> \
npx next dev -p 3007
```

Then open `/research/reports/600760-2026H1?q=<question>`. A management question
shows the packet and form; an admitted claim shows the development report.

## Before customer-facing publication

1. Designate a qualified, independent reviewer (allowlist entry, identity,
   process) and a production authentication model.
2. Extend the review contract to synthesized claims and batch review if needed.
3. Validate on a second authorized document.
4. Add an offline evaluation for packet/reuse behavior and review quality.
