"""One-question, source-text-only Q&A baseline. NOT an LLM or semantic reviewer.

No inference, cross-period comparison, valuation, model keys or benchmark GT.
An independent deterministic reviewer admits literal source-transcription
claims only. Research publication remains blocked regardless of this admission.
"""

from datetime import datetime
from hashlib import sha256
from zoneinfo import ZoneInfo

from app.evidence import preview
from app.modules.financial_report_analyst.contracts import (
    ClaimKind,
    ClaimReview,
    ResearchClaim,
    ReviewVerdict,
)

QUESTION = "What do the revenue and cost rows in the 2026H1 segment table say?"
QUESTION_KEY = "600760_2026H1_SEGMENT_ROWS_SOURCE_ONLY_V1"
QUESTION_VARIANTS = frozenset({
    QUESTION.casefold(),
    "what is shown in the 2026h1 segment revenue and cost rows?",
    "2026h1报告第198页分部营业收入和营业成本两行写了什么？",
})

# Deliberately explicit because a PDF text extraction cannot establish columns.
ROW_RULES = (
    ("C1", "segment-revenue-row", "一、营业收入", "6,191,107,217.36"),
    ("C2", "segment-cost-row", "二、营业成本", "5,535,215,299.31"),
)
REVIEWER_ID = "source-text-literal-reviewer-v1"


def supports_question(question: str) -> bool:
    return " ".join(question.strip().split()).casefold() in QUESTION_VARIANTS


def _literal_claim(claim_id: str, evidence_id: str, label: str, value: str) -> ResearchClaim:
    return ResearchClaim(
        claim_id=claim_id,
        kind=ClaimKind.OBSERVED_FACT,
        text=f'The segment-disclosure row labeled "{label}" contains the text "{value}".',
        evidence_ids=(evidence_id,),
    )


def draft_claims(evidence: list[dict]) -> tuple[ResearchClaim, ...]:
    """Bounded template-based Analyst, not generative model reasoning."""
    ids = {item["evidence_id"] for item in evidence}
    if len(ids) != len(evidence):
        raise ValueError("DUPLICATE_EVIDENCE")
    if ids != {rule[1] for rule in ROW_RULES}:
        raise ValueError("MISSING_REQUIRED_EVIDENCE")
    return tuple(_literal_claim(*rule) for rule in ROW_RULES)


def review_claims(
    claims: tuple[ResearchClaim, ...], evidence: list[dict]
) -> tuple[ClaimReview, ...]:
    """Separate restrictive Reviewer. Source-text match only; NO finance semantics."""
    refs = {item["evidence_id"]: item for item in evidence}
    if len(refs) != len(evidence):
        raise ValueError("DUPLICATE_EVIDENCE")
    allowed = {rule[0]: rule for rule in ROW_RULES}
    decisions = []
    for claim in claims:
        rule = allowed.get(claim.claim_id)
        ok = rule is not None
        if ok:
            _, evidence_id, label, number = rule
            item = refs.get(evidence_id)
            expected = _literal_claim(*rule)
            ok = (
                item is not None
                and claim == expected
                and claim.kind == ClaimKind.OBSERVED_FACT
                and claim.evidence_ids == (evidence_id,)
                and item.get("document_id") == preview.DOCUMENT_ID
                and item.get("canonical_sha256") == preview.SOURCE.canonical_sha256
                and item.get("page_number") == preview.PAGE_NUMBER
                and isinstance(item.get("excerpt"), str)
                and label in item["excerpt"]
                and number in item["excerpt"]
                and item["excerpt"].index(label) < item["excerpt"].index(number)
            )
        decisions.append(ClaimReview(
            claim_id=claim.claim_id,
            reviewer_id=REVIEWER_ID,
            verdict=ReviewVerdict.ADMIT if ok else ReviewVerdict.REJECT,
            rationale=(
                "Literal source-text transcription verified; no financial column meaning reviewed."
                if ok else "Literal evidence or claim-template mismatch."
            ),
        ))
    return tuple(decisions)


def _withhold(reason: str, status: str = "WITHHELD") -> dict:
    return {
        "status": status,
        "reason": reason,
        "answer_scope": "SOURCE_TEXT_ONLY",
        "research_publication": "BLOCKED",
        "claims": [],
        "reviews": [],
        "evidence": [],
    }


def answer_question(question: str) -> dict:
    if not supports_question(question):
        return _withhold("Only the documented segment-row transcription question is supported.", "UNSUPPORTED")

    # This function independently verifies the actual local PDF and exact spans.
    packet = preview.build_source_preview(preview.PDF_PATH)
    if packet["status"] != "SOURCE_EVIDENCE_ONLY" or packet["financial_semantic_review"] != "NOT_PERFORMED":
        raise ValueError("SOURCE_STATUS_UNEXPECTED")
    evidence = packet["evidence"]
    claims = draft_claims(evidence)
    reviews = review_claims(claims, evidence)

    if (
        len(claims) != len(ROW_RULES)
        or len(reviews) != len(claims)
        or {c.claim_id for c in claims} != {rule[0] for rule in ROW_RULES}
        or {c.claim_id for c in claims} != {r.claim_id for r in reviews}
        or any(r.verdict != ReviewVerdict.ADMIT for r in reviews)
    ):
        return _withhold("Independent source-text review did not admit every claim.")

    answer_id = sha256((
        packet["document_id"] + "|" + packet["canonical_sha256"] + "|" + QUESTION_KEY
    ).encode("utf-8")).hexdigest()
    return {
        "status": "SOURCE_ANSWER_READY",
        "answer_scope": "SOURCE_TEXT_ONLY",
        "research_publication": "BLOCKED",
        "financial_semantic_review": "NOT_PERFORMED",
        "review_scope": "LITERAL_SOURCE_TEXT_ONLY",
        "question": question,
        "answer_id": answer_id,
        "generated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "document_id": packet["document_id"],
        "report_period": packet["report_period"],
        "ticker": packet["ticker"],
        "source_url": packet["source_url"],
        "source_sha256": packet["source_sha256"],
        "canonical_sha256": packet["canonical_sha256"],
        "claims": [c.model_dump(mode="json") for c in claims],
        "reviews": [r.model_dump(mode="json") for r in reviews],
        "evidence": evidence,
        "limitation": packet["limitation"],
    }
