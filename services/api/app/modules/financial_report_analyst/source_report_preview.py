"""M112B: one source-bound, unpublished financial research report preview.

Combines verified literal statement cells and a verified management passage.
No model, financial-semantic ADMIT, persistence, or publication.
"""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from app.modules.financial_report_analyst import (
    management_evidence,
    revenue_scope,
)

VERSION = "m112b-source-report-preview-v1"
REPORT_KEY = "600276-2026H1"
QUESTION_CODE = "revenue_and_innovation_source_context_2026H1"
QUESTION = (
    "What revenue-labelled source rows and innovative-drug sales "
    "discussion appear in Hengrui's 2026 H1 disclosure, "
    "and what interpretation remains unqualified?"
)


def build_source_report(
    pdf_path: Path,
    *,
    as_of: datetime,
) -> dict:
    """Assemble verified source observations; withhold interpretation."""
    source = revenue_scope.SOURCE
    source.require_available(as_of)

    draft = revenue_scope.build_source_draft(
        source, pdf_path, as_of=as_of,
    )
    if (
        draft.get("status") != "SOURCE_DRAFT_READY"
        or draft.get("research_publication") != "BLOCKED"
        or draft.get("financial_semantic_review") != "NOT_PERFORMED"
        or draft.get("document_id") != source.document_id
        or draft.get("source_sha256") != source.source_sha256
        or draft.get("canonical_sha256") != source.canonical_sha256
        or draft.get("source_url") != source.source_url
    ):
        raise ValueError("SOURCE_DRAFT_NOT_QUALIFIED")

    expected_source_id = sha256(
        (
            source.document_id
            + "|" + source.canonical_sha256
            + "|revenue-scope-preview-v1"
        ).encode()
    ).hexdigest()

    if draft.get("report_id") != expected_source_id:
        raise ValueError("SOURCE_DRAFT_IDENTITY_MISMATCH")

    observations = draft.get("observations")
    claims = draft.get("claims")
    reviews = draft.get("reviews")

    if not all(
        isinstance(items, list) and len(items) == 2
        for items in (observations, claims, reviews)
    ):
        raise ValueError("SOURCE_CLAIM_GRAPH_INVALID")

    facts = []
    seen_evidence = set()

    for i, (obs, claim, review, selection) in enumerate(
        zip(
            observations,
            claims,
            reviews,
            revenue_scope.SELECTIONS,
        ),
        start=1,
    ):
        if not all(
            isinstance(item, dict)
            for item in (obs, claim, review)
        ):
            raise ValueError("INVALID_SOURCE_RECORD")

        evidence_id = obs.get("evidence_id")
        claim_id = f"REV{i}"

        if (
            not isinstance(evidence_id, str)
            or not re.fullmatch(r"[0-9a-f]{64}", evidence_id)
            or evidence_id in seen_evidence
            or obs.get("claim_id") != claim_id
            or claim.get("claim_id") != claim_id
            or claim.get("kind") != "OBSERVED_FACT"
            or claim.get("evidence_ids") != [evidence_id]
            or review.get("claim_id") != claim_id
            or review.get("verdict") != "ADMIT"
            or review.get("reviewer_id")
                != "native-pdf-cell-literal-reviewer-v1"
            or review.get("rationale")
                != "LITERAL_CELL_AND_HEADING_SOURCE_CHECK_ONLY"
            or obs.get("statement_type_candidate")
                != selection["section_kind"]
            or revenue_scope._norm(obs.get("row_label", ""))
                != revenue_scope._norm(selection["row_label"])
            or revenue_scope._norm(obs.get("column_header", ""))
                != revenue_scope._norm(selection["column_header"])
            or obs.get("review_scope")
                != "LITERAL_CELL_LOCATION_ONLY"
            or obs.get("source_text_span_status")
                != "NOT_PROVEN_FROM_TABLE_GEOMETRY"
            or not isinstance(obs.get("page_number"), int)
            or isinstance(obs["page_number"], bool)
            or obs["page_number"] < 1
        ):
            raise ValueError("SOURCE_OBSERVATION_BINDING_INVALID")

        expected_text = (
            f'In the source section "{obs["statement_title"]}", '
            f'the row "{obs["row_label"]}" under '
            f'"{obs["column_header"]}" reads '
            f'"{obs["value_verbatim"]}".'
        )
        if claim.get("text") != expected_text:
            raise ValueError("SOURCE_CLAIM_TEXT_MISMATCH")

        seen_evidence.add(evidence_id)

        facts.append({
            "claim_id": claim_id,
            "kind": "SOURCE_LITERAL_OBSERVATION",
            "text": expected_text,
            "evidence_id": evidence_id,
            "page": obs["page_number"],
            "statement_title": obs["statement_title"],
            "row_label": obs["row_label"],
            "column_header": obs["column_header"],
            "value_verbatim": obs["value_verbatim"],
            "statement_context": obs["statement_context"],
            "review_result": "SOURCE_LOCATION_VERIFIED_ONLY",
            "review_scope": obs["review_scope"],
        })

    management = management_evidence.locate_management_excerpt(
        pdf_path, as_of=as_of,
    )

    passage = management.get("passage_whitespace_normalized", "")
    page = management.get("source_page")
    evidence_id = management.get("evidence_id")

    if (
        management.get("status") != "SOURCE_PASSAGE_REVIEWED"
        or management.get("source_kind")
            != "MANAGEMENT_DISCUSSION_PASSAGE"
        or management.get("review_scope")
            != "NATIVE_PDF_TEXT_AND_WORD_LOCATION_ONLY"
        or management.get("document_id") != source.document_id
        or management.get("source_sha256") != source.source_sha256
        or management.get("canonical_sha256")
            != source.canonical_sha256
        or management.get("source_url") != source.source_url
        or management.get("research_publication") != "BLOCKED"
        or management.get("financial_semantic_review")
            != "NOT_PERFORMED"
        or not isinstance(page, int)
        or isinstance(page, bool)
        or page < 1
        or not isinstance(passage, str)
        or management_evidence._SENTENCE.fullmatch(passage) is None
        or not isinstance(evidence_id, str)
    ):
        raise ValueError("MANAGEMENT_SOURCE_NOT_QUALIFIED")

    expected_evidence_id = sha256(
        "|".join((
            source.document_id,
            source.canonical_sha256,
            str(page),
            "management-innovation-sales-v1",
            passage,
        )).encode()
    ).hexdigest()

    if (
        evidence_id != expected_evidence_id
        or evidence_id in seen_evidence
    ):
        raise ValueError("MANAGEMENT_EVIDENCE_BINDING_INVALID")

    effective_date = as_of.astimezone(
        ZoneInfo("Asia/Shanghai")
    ).date().isoformat()

    identity_payload = {
        "version": VERSION,
        "question_code": QUESTION_CODE,
        "document_id": source.document_id,
        "canonical_sha256": source.canonical_sha256,
        "as_of_date": effective_date,
        "source_draft_id": draft["report_id"],
        "evidence": [
            (f["evidence_id"], f["value_verbatim"])
            for f in facts
        ] + [(evidence_id, passage)],
    }

    report_identity = sha256(
        json.dumps(
            identity_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    return {
        "status": "LOCAL_SOURCE_REPORT_READY",
        "report_type": "UNPUBLISHED_SOURCE_REPORT_PREVIEW",
        "report_key": REPORT_KEY,
        "report_identity": report_identity,
        "source_draft_id": draft["report_id"],
        "report_storage": "NOT_PERSISTED",
        "question_code": QUESTION_CODE,
        "question": QUESTION,
        "issuer_name": "恒瑞医药",
        "report_period": source.report_period,
        "as_of": as_of.isoformat(),
        "generated_at": datetime.now(
            ZoneInfo("Asia/Shanghai")
        ).isoformat(),
        "document_id": source.document_id,
        "source_url": source.source_url,
        "source_sha256": source.source_sha256,
        "canonical_sha256": source.canonical_sha256,
        "observations": facts,
        "management_statement": {
            "claim_id": "M1",
            "kind": "ATTRIBUTED_MANAGEMENT_STATEMENT",
            "text": passage,
            "evidence_id": evidence_id,
            "page": page,
            "review_result": "SOURCE_PASSAGE_LOCATED_ONLY",
            "review_scope": management["review_scope"],
        },
        "analyst_interpretation": {
            "status": "WITHHELD",
            "reason": "FINANCIAL_SEMANTIC_REVIEW_NOT_PERFORMED",
        },
        "financial_semantic_review": "NOT_PERFORMED",
        "research_publication": "BLOCKED",
        "limitations": [
            "Statement cells are verified literal source observations.",
            "Management statements are attributed, not independently endorsed.",
            "No financial comparability, causality, inference, or publication is approved.",
        ],
    }
