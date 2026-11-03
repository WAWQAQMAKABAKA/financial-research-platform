"""M1 facts-only disclosure report for one authorized corpus document.

Reuses the existing M1.7A extraction/reviewer path (one literal cell, one
independent literal review) and adds the missing layer: a publication decision.
The report is not persisted, calls no model, and publishes only OBSERVED_FACT
claims that the facts-only policy approves. Everything comparative, inferential
or unreviewed is withheld and listed as such.

Document identity comes from the tracked corpus manifest, never from a literal
in this file.
"""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from pathlib import Path

from app.evidence import corpus_manifest
from app.modules.financial_report_analyst import publication_policy, source_workspace

REPORT_TYPE = "FACTS_ONLY_DISCLOSURE_REPORT"
REPORT_VERSION = "m1-600760-facts-report-v1"
QUESTION_CODE = "consolidated_income_statement_row_2026H1"
QUESTION = (
    "600760 中航沈飞 2026 年半年度合并利润表中，"
    "「其中：营业收入」在「2026 年半年度」列披露的金额是多少？"
)

LIMITATIONS = (
    "每条事实均为披露原文的逐字定位，未进行财务语义核验（financial_semantic_review = NOT_PERFORMED）。",
    "仅展示「合并利润表 · 其中：营业收入 · 2026 年半年度」一行，不代表完整利润表或公司整体经营情况。",
    "本报告不包含跨期比较、跨主体比较、推断、前瞻或管理层解释；这些能力未获批准。",
    "金额单位为元、币种为人民币，均取自披露原文上下文，未经会计口径核验。",
    "报告按请求即时生成，未持久化，也未对外发布；原始 PDF 不进入代码仓库。",
)


def supported_report_keys() -> tuple[str, ...]:
    return tuple(sorted(
        key for key, entry in source_workspace.REPORTS.items()
        if entry.authorization == source_workspace.AUTHORIZATION_MANIFEST
    ))


def _report_id(document: corpus_manifest.CorpusDocument) -> str:
    return sha256(
        f"{document.document_id}|{document.canonical_sha256}|{REPORT_VERSION}".encode()
    ).hexdigest()


def _withheld(
    report_key: str,
    reason: str,
    *,
    decision: dict | None = None,
    document: corpus_manifest.CorpusDocument | None = None,
) -> dict:
    publication = decision or {
        "policy_version": publication_policy.POLICY_VERSION,
        "status": "PUBLICATION_WITHHELD",
        "may_publish": False,
        "research_publication": publication_policy.BLOCKED,
        "publication_label": publication_policy.PUBLICATION_LABEL,
        "financial_semantic_review": "NOT_PERFORMED",
        "published_claim_ids": [],
        "withheld": [],
        "withheld_capabilities": [
            {"kind": kind, "status": "NOT_PUBLISHED", "reason": text}
            for kind, text in publication_policy.WITHHELD_CAPABILITIES
        ],
        "reason": reason,
    }
    return {
        "status": "REPORT_WITHHELD",
        "reason": reason,
        "report_type": REPORT_TYPE,
        "report_version": REPORT_VERSION,
        "report_key": report_key,
        "report_id": None,
        "issuer": None if document is None else {
            "name": document.issuer_name,
            "ticker": document.ticker,
            "report_period": document.report_period,
        },
        "source": None,
        "request": None,
        "facts": [],
        "reviews": [],
        "publication": publication,
        "limitations": list(LIMITATIONS),
        "report_storage": "NOT_PERSISTED",
    }


def build_report(report_key: str, pdf_path: Path, *, as_of: datetime) -> dict:
    """Build one facts-only report or return a withheld report with no facts."""
    entry = source_workspace.REPORTS.get(report_key)
    if entry is None or entry.authorization != source_workspace.AUTHORIZATION_MANIFEST:
        raise source_workspace.UnknownReportError("REPORT_NOT_AUTHORIZED_IN_CORPUS")

    document = corpus_manifest.load_corpus_manifest().require_report_key(report_key)
    if document.to_source_document() != entry.source:
        raise ValueError("MANIFEST_SOURCE_IDENTITY_MISMATCH")

    # Bytes, not the path, are the identity. Missing or altered PDFs raise.
    corpus_manifest.verify_document(document, pdf_path=Path(pdf_path))

    try:
        draft = source_workspace.build_source_workspace(
            report_key, Path(pdf_path), as_of=as_of,
        )
    except ValueError as exc:
        if str(exc) == "PIT_UNAVAILABLE":
            return _withheld(report_key, "PIT_UNAVAILABLE", document=document)
        raise
    if draft.get("status") != "SOURCE_DRAFT_READY":
        return _withheld(
            report_key, str(draft.get("reason") or "SOURCE_DRAFT_NOT_READY"),
            document=document,
        )

    decision = publication_policy.decide_publication(
        draft, document,
        expected_statement_kind=entry.section_kind,
        expected_row_label=entry.row_label,
        as_of=as_of,
    )
    if not decision.get("may_publish"):
        return _withheld(
            report_key, str(decision.get("reason") or "PUBLICATION_WITHHELD"),
            decision=decision, document=document,
        )

    published = set(decision["published_claim_ids"])
    facts = []
    for claim, observation in zip(draft["claims"], draft["observations"]):
        if claim["claim_id"] not in published:
            continue
        facts.append({
            "claim_id": claim["claim_id"],
            "kind": claim["kind"],
            "statement_title": observation["statement_title"],
            "statement_type": observation["statement_type_candidate"],
            "row_label": observation["row_label"],
            "column_header": observation["column_header"],
            "value_verbatim": observation["value_verbatim"],
            "statement_context": observation["statement_context"],
            "page_number": observation["page_number"],
            "evidence_id": observation["evidence_id"],
            "citation": {
                "document_id": document.document_id,
                "page_number": observation["page_number"],
                "source_url": document.source_url,
                "source_sha256": document.source_sha256,
                "canonical_sha256": document.canonical_sha256,
                "cell_bbox_pt": observation.get("cell_bbox_pt"),
            },
        })

    reviews = [{
        "claim_id": review["claim_id"],
        "verdict": review["verdict"],
        "reviewer_id": review["reviewer_id"],
        "rationale": review["rationale"],
        "review_scope": publication_policy.LITERAL_REVIEW_SCOPE,
    } for review in draft["reviews"] if review["claim_id"] in published]

    if len(facts) != len(published) or len(reviews) != len(published):
        raise ValueError("PUBLISHED_CLAIM_GRAPH_INCONSISTENT")

    source = document.to_source_document()
    return {
        "status": "REPORT_READY",
        "reason": None,
        "report_type": REPORT_TYPE,
        "report_version": REPORT_VERSION,
        "report_key": report_key,
        "report_id": _report_id(document),
        "issuer": {
            "name": document.issuer_name,
            "ticker": document.ticker,
            "report_period": document.report_period,
        },
        "source": {
            "document_id": document.document_id,
            "source_url": document.source_url,
            "published_on": document.published_on.isoformat(),
            "pit_available_at": source.pit_available_at.isoformat(),
            "source_sha256": document.source_sha256,
            "canonical_sha256": document.canonical_sha256,
            "page_count": document.page_count,
            "authorization_note": document.authorization_note,
        },
        "request": {
            "question_code": QUESTION_CODE,
            "question": QUESTION,
        },
        "facts": facts,
        "reviews": reviews,
        "publication": decision,
        "limitations": list(LIMITATIONS),
        "report_storage": "NOT_PERSISTED",
    }
