# ADR 0005 — Bounded source Q&A development baseline

Status: PROPOSED; requires real-PDF, frontend and negative-path acceptance.

M1.4A offers one user-entered question about the 2026H1 page-198
reporting-segment **revenue-labeled and cost-labeled text rows** for 600760.
This is not an open-ended chatbot and not a financial-semantic answer.

The Analyst is a deterministic literal-claim template, and the separately
implemented Reviewer admits only exact source-text references and the fixed
literal templates. `ADMIT` here means **source-text transcription only**.
It is NOT an LLM or independent financial-semantic judgment. The source
builder re-verifies the ignored original PDF/hash, canonical hash and
page/offset bindings for every supported question.

The UI shows both claims and original PDF links. A mismatch, absence of PDF,
unsupported question, disabled API or failed review must never expose
unreviewed claims. Research publication is always BLOCKED, including when
both literal claims are admitted. No persisted report or multi-turn chat yet.

Feature flag `FRP_LOCAL_RESEARCH_QA=1` is for local `127.0.0.1` use only.
The unauthenticated endpoint MUST NOT be deployed. No protected evaluation
content, external model credentials, trading state, or legacy runtime imports.
Future M1.4B: model-backed Analyst, genuinely independent finance-semantic
Reviewer, report identity/persistence, publication gate and end-to-end review.
