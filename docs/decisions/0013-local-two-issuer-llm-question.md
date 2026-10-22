# ADR 0013 — M1.7B local-only source question with DeepSeek

Date: 2026-10-22
Status: PROPOSED — full Mac regression, real original-PDF API/browser and paid calls pending

## Customer-visible narrow slice

`/research/source-workspace/ask`: choose either hash-pinned original 2026 H1 report
(600276 恒瑞医药 or 600760 中航沈飞). Ask exactly one allowlisted question:
what the selected consolidated income-statement revenue source row reads.
The model proposes **one literal cell binding**; the answer sentence is generated
by code from independently checked source fields. No arbitrary prompts, new
metrics, growth comparisons, portfolio analysis or investment recommendations.

The existing shared source-workspace builder performs PIT and original-PDF / canonical
SHA verification, structural attribution and independent native-PDF literal review
before any paid model call. DeepSeek `deepseek-flash` receives only the public
source packet; exact JSON bindings and usage are checked on return. Any unknown
source/metric/evidence, changed value, provider error or incomplete response
withholds claims. Claim identity includes the verified source report digest.
No runtime benchmark GT or expected real-report values.

## Paid-call boundary

Disabled by default at both Next.js and FastAPI. The local launcher binds both
servers to `127.0.0.1`, prompts for the DeepSeek key without echoing it, passes it
only to FastAPI's child environment, and creates a different ephemeral session
secret shared by the two servers. The browser receives neither credential.
The Next.js POST broker checks same-origin, exact report/question JSON, dev mode,
and forwards with its private token. The FastAPI POST checks a constant-time
session token and both feature flags, serializes original PDF work, releases the
PDF lock **before network I/O**, and permits at most four paid attempts per
process session. No retries or automatic calls. Keys remain in process memory;
this is local development, NOT production authentication or deployment.

The source-literal Reviewer ADMIT is not an accounting interpretation. The model
cannot approve claims. `financial_semantic_review=NOT_PERFORMED` and
`research_publication=BLOCKED` always. Real-document qualification and independent
financial-semantic review are subsequent steps; this UI MUST NOT be marketed as
an approved customer report.

## Acceptance

Synthetic network-free provider and HTTP gate regression, original-PDF audit
for both issuers, production Next build/lint, browser explicit click for both,
working PDF citations, sanitized failures, no unintended paid retries, and
local + GitHub commit verification. Do not commit if canonical hash changes,
false financial semantics, or lost fail-closed publication occur.
