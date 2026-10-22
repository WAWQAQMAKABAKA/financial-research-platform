"""M1.8A: one source-PDF, two separately bound literal revenue observations.

This is a local, non-published evidence briefing, NOT a financial analysis.
Source verification, literal review and the paid model binding step are
reused from the preexisting Hengrui pipeline. No benchmark answer in runtime.
"""
from __future__ import annotations

from hashlib import sha256

import httpx

from app.modules.financial_report_analyst import deepseek_draft, revenue_scope

QUESTION_CODE = "revenue_rows_two_scopes_2026H1"
QUESTION = (
    "What revenue-labelled source rows appear in the consolidated and "
    "parent-company income statements of Hengrui's 2026 H1 disclosure?"
)
BRIEF_VERSION = "two-source-revenue-brief-v1"


def _withheld(reason: str, usage: dict | None = None) -> dict:
    result = {
        "status": "WITHHELD", "reason": reason, "claims": [], "reviews": [],
        "financial_semantic_review": "NOT_PERFORMED",
        "research_publication": "BLOCKED",
    }
    if usage is not None:
        result["usage"] = usage
    return result


def draft_two_source_brief(
    source_draft: dict, *, api_key: str, client: httpx.Client | None = None,
) -> dict:
    """Each displayed statement is reconstructed from two native-PDF-reviewed cells.

    The LLM only proposes exact IDs/values and cannot author the displayed
    explanation, change financial meaning or authorize publication.
    """
    try:
        # This function requires the pinned source-draft identity and the
        # independent ADMIT literal-location verdict for *both* observations.
        packet = deepseek_draft._verified_packet(source_draft)
        evidence = packet["evidence"]
        if (len(evidence) != 2
            or evidence[0]["statement_kind"] != "consolidated_income_statement"
            or evidence[1]["statement_kind"] != "parent_income_statement"
            or evidence[0]["evidence_id"] == evidence[1]["evidence_id"]):
            return _withheld("TWO_SOURCE_SCOPE_NOT_QUALIFIED")
    except (ValueError, KeyError, TypeError, AttributeError):
        return _withheld("SOURCE_NOT_QUALIFIED")

    # Exactly one provider request, no retries. Existing independent binding
    # validator withholds *all* model claims on any mismatch.
    model = deepseek_draft.draft_verified_cells(
        source_draft, api_key=api_key, client=client,
    )
    if model.get("status") != "LLM_PROPOSAL_PACKET_MATCHED":
        return _withheld(model.get("reason", "MODEL_NOT_QUALIFIED"), model.get("usage"))
    proposed = model.get("claims")
    if (not isinstance(proposed, list) or len(proposed) != 2
        or model.get("source_report_id") != source_draft.get("report_id")
        or model.get("document_id") != revenue_scope.SOURCE.document_id
        or model.get("source_sha256") != revenue_scope.SOURCE.source_sha256
        or model.get("canonical_sha256") != revenue_scope.SOURCE.canonical_sha256
        or model.get("research_publication") != "BLOCKED"
        or model.get("financial_semantic_review") != "NOT_PERFORMED"):
        return _withheld("PROPOSAL_IDENTITY_INVALID", model.get("usage"))

    claims = []
    reviews = []
    for i, (p, item) in enumerate(zip(proposed, evidence)):
        claim_id = f"DS{i + 1}"
        if (not isinstance(p, dict)
            or p.get("claim_id") != claim_id
            or p.get("evidence_id") != item["evidence_id"]
            or p.get("source_page") != item["page_number"]
            or p.get("statement_kind") != item["statement_kind"]
            or p.get("verification") != "EXACT_MATCH_TO_PREVERIFIED_LITERAL_PACKET"):
            return _withheld("CLAIM_REVIEW_BINDING_MISMATCH", model.get("usage"))
        claims.append({
            "claim_id": claim_id,
            "kind": "OBSERVED_FACT",
            "evidence_id": item["evidence_id"],
            "source_page": item["page_number"],
            "statement_kind_candidate": item["statement_kind"],
            "statement_title": item["statement_title"],
            "row_label": item["row_label"],
            "column_header": item["column_header"],
            "value_verbatim": item["value"],
            "text": (
                f'In the source section "{item["statement_title"]}", '
                f'the row "{item["row_label"]}" under '
                f'"{item["column_header"]}" reads "{item["value"]}".'
            ),
        })
        reviews.append({
            "claim_id": claim_id,
            "evidence_id": item["evidence_id"],
            "verdict": "LITERAL_LOCATION_MATCH_ONLY",
            "review_scope": "NATIVE_PDF_TEXT_AND_EXACT_LLM_BINDING",
            "financial_semantic_review": "NOT_PERFORMED",
        })

    return {
        "status": "LLM_MULTI_EVIDENCE_PACKET_MATCHED",
        "question": QUESTION,
        "question_code": QUESTION_CODE,
        "report_key": "600276-2026H1",
        "document_id": revenue_scope.SOURCE.document_id,
        "source_url": revenue_scope.SOURCE.source_url,
        "source_sha256": revenue_scope.SOURCE.source_sha256,
        "canonical_sha256": revenue_scope.SOURCE.canonical_sha256,
        "source_report_id": source_draft["report_id"],
        "llm_draft_id": sha256((source_draft["report_id"] + "|" +
            BRIEF_VERSION + "|" + model["llm_draft_id"]).encode()).hexdigest(),
        "model": model["model"],
        "brief": (
            "The disclosure has separate revenue-labelled rows in its "
            "consolidated and parent-company income-statement sections. "
            "These are two distinct source observations, not a comparison "
            "or a conclusion about their accounting relationship."
        ),
        "claims": claims,
        "reviews": reviews,
        "usage": model["usage"],
        "financial_semantic_review": "NOT_PERFORMED",
        "research_publication": "BLOCKED",
        "limitation": (
            "Source-text and location checks only; interpretation of statement "
            "scope, comparability, performance and financial meaning is not qualified."
        ),
    }
