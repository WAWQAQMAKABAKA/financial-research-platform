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
import re
import unicodedata

import pymupdf

from app.evidence import corpus_manifest, document_index
from app.evidence.cell_attribution import locate_cells_in_verified_pdf
from app.modules.financial_report_analyst.contracts import (
    ClaimKind,
    ClaimReview,
    ResearchClaim,
    ReviewVerdict,
)
from app.modules.financial_report_analyst import (
    canonical_retrieval,
    clarification,
    evidence_plan,
    interpretation,
    intent_gate,
    publication_policy,
    semantic_review,
    question_selection,
    revenue_scope,
    source_workspace,
)

REPORT_TYPE = "FACTS_ONLY_DISCLOSURE_REPORT"
REPORT_VERSION = "m1-600760-facts-report-v1"
QUESTION_CODE = "consolidated_income_statement_row_2026H1"
QUESTION = (
    "600760 中航沈飞 2026 年半年度合并利润表中，"
    "「其中：营业收入」在「2026 年半年度」列披露的金额是多少？"
)

ASK_VERSION = "m2a-600760-question-report-v1"
MAX_QUESTION_CHARS = 240

ASK_LIMITATIONS = (
    "每条事实均为披露原文的逐字定位，未进行财务语义核验（financial_semantic_review = NOT_PERFORMED）。",
    "报表范围由问题中的报表名称或检索结果确定；行项目由问题与原文行标签的词法匹配确定，不是语义理解。",
    "只支持 600760 2026 年半年度合并利润表/母公司利润表的金额行；跨期、跨主体与比较不发布。",
    "问题未命中唯一行项目、或命中过多时，报告整体不发布，并显示未命中的原因。",
    "报告按请求即时生成，未持久化，也未对外发布；原始 PDF 不进入代码仓库。",
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
    extra: dict | None = None,
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
        **(extra or {}),
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


def _retrieval_trace(retrieval: dict, *, include_excerpts: bool = False) -> dict:
    """Ranked candidates. Excerpts are only attached to published reports."""
    hits = retrieval.get("evidence")
    return {
        "status": retrieval.get("status"),
        "retriever_version": retrieval.get("retriever_version"),
        "hits": [
            {
                "page_number": hit.get("source_page"),
                "evidence_id": hit.get("evidence_id"),
                "excerpt": (
                    (hit.get("source_excerpt") or "").strip()[:180]
                    if include_excerpts else ""
                ),
            }
            for hit in (hits if isinstance(hits, list) else [])[:5]
        ],
    }


def _selection_trace(selection: dict) -> dict:
    return {
        "status": selection.get("status"),
        "reason": selection.get("reason"),
        "version": selection.get("version"),
        "statement_kind": selection.get("statement_kind"),
        "column_header": selection.get("column_header"),
        "rows": [row.get("row_label") for row in selection.get("rows", [])],
        "trace": selection.get("trace"),
    }


def _fact_rows(draft: dict, document: corpus_manifest.CorpusDocument) -> list[dict]:
    facts = []
    for claim, observation in zip(draft["claims"], draft["observations"]):
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
    return facts


def build_report_from_question(
    report_key: str,
    pdf_path: Path,
    question: str,
    *,
    as_of: datetime,
    forced_selection: dict | None = None,
    forced_statement_kind: str | None = None,
) -> dict:
    """Question -> retrieval -> statement rows -> verified cells -> policy.

    The question selects *which* rows are cited; it never decides whether they
    are true. Every citation is re-located in the native PDF and re-checked by
    the literal reviewer before the policy may publish it.

    ``forced_selection`` carries a user-resolved metric (from a clarification):
    ``{"statement_kind", "row_label", "core"}``. It bypasses only the row
    selection, never the identity, retrieval, literal review or publication.
    """
    entry = source_workspace.REPORTS.get(report_key)
    if entry is None or entry.authorization != source_workspace.AUTHORIZATION_MANIFEST:
        raise source_workspace.UnknownReportError("REPORT_NOT_AUTHORIZED_IN_CORPUS")

    document = corpus_manifest.load_corpus_manifest().require_report_key(report_key)
    if document.to_source_document() != entry.source:
        raise ValueError("MANIFEST_SOURCE_IDENTITY_MISMATCH")

    if (not isinstance(question, str) or not question.strip()
            or len(question) > MAX_QUESTION_CHARS):
        return _withheld(
            report_key, "QUESTION_INVALID", document=document,
            extra={"request": {"question": question, "question_code": None}},
        )

    path = Path(pdf_path)
    corpus_manifest.verify_document(document, pdf_path=path)

    # P0: a comparison, forecast or unclassifiable question never reaches
    # retrieval, selection or publication, even if it contains a row's words.
    intent = intent_gate.classify_intent(question)
    intent_block = {"value": intent.value, "version": intent_gate.INTENT_VERSION}
    if intent is not intent_gate.Intent.FACT_LOOKUP:
        return _withheld(
            report_key, str(intent_gate.rejection_reason(intent)),
            document=document,
            extra={"request": {"question": question, "question_code": None},
                   "intent": intent_block},
        )

    try:
        retrieval = canonical_retrieval.retrieve_report_evidence(
            entry.source, path, question, as_of=as_of,
        )
    except ValueError as exc:
        return _withheld(
            report_key, str(exc) or "RETRIEVAL_FAILED", document=document,
            extra={"request": {"question": question, "question_code": None}},
        )

    retrieval_trace = _retrieval_trace(retrieval)
    if retrieval.get("status") != "RETRIEVAL_CANDIDATES_READY":
        return _withheld(
            report_key, "RETRIEVAL_NOT_READY", document=document,
            extra={"request": {"question": question, "question_code": None},
                   "retrieval": retrieval_trace},
        )

    expected = publication_policy.period_expectations(document.report_period)
    if expected is None:
        return _withheld(
            report_key, "UNSUPPORTED_REPORT_PERIOD", document=document,
            extra={"request": {"question": question, "question_code": None}},
        )
    column_header = expected[0]

    try:
        index = document_index.index_document_scoped(
            entry.source, path, as_of=as_of,
            section_kinds=frozenset(question_selection.INCOME_STATEMENT_KINDS),
        )
    except ValueError as exc:
        return _withheld(
            report_key, str(exc) or "INDEX_SCOPE_FAILED", document=document,
            extra={"request": {"question": question, "question_code": None},
                   "retrieval": retrieval_trace},
        )

    if forced_selection is not None:
        selection = {
            "status": "SELECTION_READY",
            "reason": None,
            "version": question_selection.SELECTION_VERSION,
            "statement_kind": forced_selection["statement_kind"],
            "column_header": column_header,
            "rows": [{
                "row_label": forced_selection["row_label"],
                "core": forced_selection["core"],
                "match_chars": len(forced_selection["core"]),
            }],
            "trace": {
                "version": question_selection.SELECTION_VERSION,
                "question": question,
                "report_period": document.report_period,
                "column_header": column_header,
                "statement_kind": forced_selection["statement_kind"],
                "statement_title": document_index.SECTION_TITLES[
                    forced_selection["statement_kind"]],
                "selection_basis": "USER_RESOLVED_METRIC",
                "row_labels_considered": 0,
                "row_candidates": [],
                "synonyms_applied": [],
                "synonym_version": question_selection.SYNONYM_VERSION,
                "normalized_question": None,
            },
        }
    else:
        selection = question_selection.select_cells(
            index, question=question, report_period=document.report_period,
            column_header=column_header, retrieval_hits=retrieval_trace["hits"],
            forced_statement_kind=forced_statement_kind,
        )
    selection_trace = _selection_trace(selection)
    if selection["status"] != "SELECTION_READY":
        return _withheld(
            report_key, str(selection.get("reason")), document=document,
            extra={"request": {"question": question, "question_code": None},
                   "retrieval": retrieval_trace, "selection": selection_trace},
        )

    selections = [
        {"section_kind": selection["statement_kind"],
         "row_label": row["row_label"], "column_header": selection["column_header"]}
        for row in selection["rows"]
    ]
    try:
        located = locate_cells_in_verified_pdf(
            entry.source, path, as_of=as_of, selections=selections,
            bounded_tables=True,
        )
    except ValueError as exc:
        return _withheld(
            report_key, str(exc) or "SOURCE_CELL_UNRESOLVED", document=document,
            extra={"request": {"question": question, "question_code": None},
                   "retrieval": retrieval_trace, "selection": selection_trace},
        )

    if len(located) != len(selections) or any(
        item.get("status") != "ONE_CELL_CANDIDATE" for item in located
    ):
        return _withheld(
            report_key, "SOURCE_CELL_UNRESOLVED", document=document,
            extra={"request": {"question": question, "question_code": None},
                   "retrieval": retrieval_trace, "selection": selection_trace},
        )

    candidates = []
    for result, chosen in zip(located, selections):
        options = result.get("candidates")
        if not isinstance(options, list) or len(options) != 1:
            return _withheld(
                report_key, "SOURCE_CELL_AMBIGUOUS", document=document,
                extra={"request": {"question": question, "question_code": None},
                       "retrieval": retrieval_trace, "selection": selection_trace},
            )
        item = options[0]
        ok, reason = question_selection.validate_candidate(
            item, entry.source,
            section_kind=chosen["section_kind"],
            row_label=chosen["row_label"],
            column_header=chosen["column_header"],
        )
        if not ok:
            return _withheld(
                report_key, reason, document=document,
                extra={"request": {"question": question, "question_code": None},
                       "retrieval": retrieval_trace, "selection": selection_trace},
            )
        candidates.append(item)

    if len({item["candidate_id"] for item in candidates}) != len(candidates):
        return _withheld(
            report_key, "DUPLICATE_SOURCE_CELL", document=document,
            extra={"request": {"question": question, "question_code": None},
                   "retrieval": retrieval_trace, "selection": selection_trace},
        )

    # A blank cell or a printed dash is not zero and must never be published.
    for item in candidates:
        raw = str(item.get("cell_text_verbatim") or "").strip()
        if not raw:
            return _withheld(
                report_key, "SOURCE_CELL_BLANK_NOT_ZERO", document=document,
                extra={"request": {"question": question, "question_code": None},
                       "retrieval": retrieval_trace, "selection": selection_trace},
            )
        if raw in {"-", "—", "–", "－", "―"}:
            return _withheld(
                report_key, "SOURCE_CELL_DASH_NOT_ZERO", document=document,
                extra={"request": {"question": question, "question_code": None},
                       "retrieval": retrieval_trace, "selection": selection_trace},
            )

    claims, reviews, observations = [], [], []
    with pymupdf.open(path) as pdf:
        for number, item in enumerate(candidates, start=1):
            claim_id = f"Q{number}"
            accepted, rationale = revenue_scope.review_literal(item, pdf)
            if not accepted:
                return _withheld(
                    report_key, "LITERAL_REVIEW_NOT_PASSED", document=document,
                    extra={"request": {"question": question, "question_code": None},
                           "retrieval": retrieval_trace, "selection": selection_trace},
                )
            claims.append(ResearchClaim(
                claim_id=claim_id, kind=ClaimKind.OBSERVED_FACT,
                text=(
                    f'在「{item["statement_heading_verbatim"]}」中，'
                    f'「{item["row_label_verbatim"]}」在'
                    f'「{item["column_header_verbatim"]}」列披露为'
                    f'「{item["cell_text_verbatim"]}」。'
                ),
                evidence_ids=(item["candidate_id"],),
            ))
            reviews.append(ClaimReview(
                claim_id=claim_id, reviewer_id="native-pdf-cell-literal-reviewer-v1",
                verdict=ReviewVerdict.ADMIT, rationale=rationale,
            ))
            observations.append({
                "claim_id": claim_id,
                "evidence_id": item["candidate_id"],
                "statement_title": item["statement_heading_verbatim"],
                "statement_type_candidate": item["section_kind_candidate"],
                "row_label": item["row_label_verbatim"],
                "column_header": item["column_header_verbatim"],
                "value_verbatim": item["cell_text_verbatim"],
                "statement_context": item["statement_context_verbatim"],
                "page_number": item["page_number"],
                "cell_bbox_pt": item["cell_bbox_pt"],
                "source_text_span_status": item["source_text_span_status"],
                "review_scope": "LITERAL_CELL_LOCATION_ONLY",
            })

    draft = {
        "status": "SOURCE_DRAFT_READY",
        "document_id": document.document_id,
        "source_sha256": document.source_sha256,
        "canonical_sha256": document.canonical_sha256,
        "source_url": document.source_url,
        "observations": observations,
        "claims": [claim.model_dump(mode="json") for claim in claims],
        "reviews": [review.model_dump(mode="json") for review in reviews],
    }

    decision = publication_policy.decide_publication(
        draft, document,
        expected_statement_kind=selection["statement_kind"],
        expected_row_labels=tuple(row["row_label"] for row in selection["rows"]),
        as_of=as_of,
    )
    if not decision.get("may_publish"):
        return _withheld(
            report_key, str(decision.get("reason") or "PUBLICATION_WITHHELD"),
            decision=decision, document=document,
            extra={"request": {"question": question, "question_code": None},
                   "retrieval": retrieval_trace, "selection": selection_trace},
        )

    published = set(decision["published_claim_ids"])
    draft_published = {
        "claims": [claim.model_dump(mode="json") for claim in claims
                   if claim.claim_id in published],
        "observations": [observation for observation in observations
                         if observation["claim_id"] in published],
    }
    facts = _fact_rows(draft_published, document)
    reviews_out = [{
        "claim_id": review.claim_id,
        "verdict": review.verdict.value,
        "reviewer_id": review.reviewer_id,
        "rationale": review.rationale,
        "review_scope": publication_policy.LITERAL_REVIEW_SCOPE,
    } for review in reviews if review.claim_id in published]

    if len(facts) != len(published) or len(reviews_out) != len(published):
        raise ValueError("PUBLISHED_CLAIM_GRAPH_INCONSISTENT")

    question_sha = sha256(question.encode("utf-8")).hexdigest()
    source = document.to_source_document()
    return {
        "status": "REPORT_READY",
        "reason": None,
        "report_type": "FACTS_ONLY_QUESTION_REPORT",
        "report_version": ASK_VERSION,
        "report_key": report_key,
        "report_id": sha256(
            f"{document.document_id}|{document.canonical_sha256}|"
            f"{ASK_VERSION}|{question_sha}".encode()
        ).hexdigest(),
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
        "request": {"question": question, "question_code": QUESTION_CODE},
        "intent": intent_block,
        "retrieval": _retrieval_trace(retrieval, include_excerpts=True),
        "selection": selection_trace,
        "facts": facts,
        "reviews": reviews_out,
        "publication": decision,
        "limitations": list(ASK_LIMITATIONS),
        "report_storage": "NOT_PERSISTED",
    }


MULTI_VERSION = "m4-multi-requirement-report-v1"


def build_multi_report(
    report_key: str,
    pdf_path: Path,
    question: str,
    *,
    as_of: datetime,
    pinned_rows: dict[str, str] | None = None,
    repair_secret: str | None = None,
    api_key: str | None = None,
) -> dict | None:
    """Two or three independent facts -> requirements -> coverage -> policy.

    Returns None when the question is not multi-fact so the caller keeps the
    single-fact path. Unsatisfied requirements are reported, never inferred.
    """
    entry = source_workspace.REPORTS.get(report_key)
    if entry is None or entry.authorization != source_workspace.AUTHORIZATION_MANIFEST:
        raise source_workspace.UnknownReportError("REPORT_NOT_AUTHORIZED_IN_CORPUS")

    document = corpus_manifest.load_corpus_manifest().require_report_key(report_key)
    if document.to_source_document() != entry.source:
        raise ValueError("MANIFEST_SOURCE_IDENTITY_MISMATCH")

    if (not isinstance(question, str) or not question.strip()
            or len(question) > MAX_QUESTION_CHARS):
        return _withheld(
            report_key, "QUESTION_INVALID", document=document,
            extra={"request": {"question": question, "question_code": None}},
        )

    path = Path(pdf_path)
    corpus_manifest.verify_document(document, pdf_path=path)

    intent = intent_gate.classify_intent(question)
    intent_block = {"value": intent.value, "version": intent_gate.INTENT_VERSION}
    if intent is not intent_gate.Intent.FACT_LOOKUP:
        return _withheld(
            report_key, str(intent_gate.rejection_reason(intent)), document=document,
            extra={"request": {"question": question, "question_code": None},
                   "intent": intent_block},
        )

    try:
        retrieval = canonical_retrieval.retrieve_report_evidence(
            entry.source, path, question, as_of=as_of,
        )
    except ValueError as exc:
        return _withheld(
            report_key, str(exc) or "RETRIEVAL_FAILED", document=document,
            extra={"request": {"question": question, "question_code": None},
                   "intent": intent_block},
        )
    retrieval_trace = _retrieval_trace(retrieval)

    expected = publication_policy.period_expectations(document.report_period)
    if expected is None:
        return _withheld(
            report_key, "UNSUPPORTED_REPORT_PERIOD", document=document,
            extra={"request": {"question": question, "question_code": None}},
        )
    column_header = expected[0]

    try:
        index = document_index.index_document_scoped(
            entry.source, path, as_of=as_of,
            section_kinds=frozenset(question_selection.INCOME_STATEMENT_KINDS),
        )
    except ValueError as exc:
        return _withheld(
            report_key, str(exc) or "INDEX_SCOPE_FAILED", document=document,
            extra={"request": {"question": question, "question_code": None},
                   "retrieval": retrieval_trace},
        )

    proposed_facets = None
    if api_key:
        proposal = interpretation.propose_facets(question, api_key=api_key)
        if proposal.get("status") == "FACETS_READY":
            proposed_facets = proposal["facets"]

    plan = evidence_plan.plan_requirements(
        index, question=question, report_period=document.report_period,
        column_header=column_header, retrieval_hits=retrieval_trace["hits"],
        pinned_rows=pinned_rows, proposed_facets=proposed_facets,
    )
    if plan is None:
        return None

    if plan["status"] == "SCOPE_AMBIGUOUS":
        return _withheld(
            report_key, "AMBIGUOUS_STATEMENT_SCOPE", document=document,
            extra={"request": {"question": question, "question_code": None},
                   "intent": intent_block, "retrieval": retrieval_trace,
                   "selection": {"status": "SELECTION_WITHHELD",
                                 "reason": "AMBIGUOUS_STATEMENT_SCOPE",
                                 "trace": {"present_statement_kinds": plan["present"]}}},
        )
    if plan["status"] != "PLAN_READY":
        extra = {"request": {"question": question, "question_code": None},
                 "intent": intent_block, "retrieval": retrieval_trace}
        if plan["status"] == "TOO_MANY_REQUIREMENTS":
            extra["plan"] = {
                "status": "TOO_MANY_REQUIREMENTS",
                "detected": plan["detected"],
                "max": plan["max"],
            }
        return _withheld(
            report_key, str(plan.get("reason") or "NO_STATEMENT_SCOPE"),
            document=document, extra=extra,
        )

    satisfied = [item for item in plan["requirements"] if item["status"] == "SATISFIED"]
    if not satisfied:
        return _withheld(
            report_key, "NO_VERIFIED_REQUIREMENT", document=document,
            extra={"request": {"question": question, "question_code": None},
                   "retrieval": retrieval_trace,
                   "coverage": {"complete": False, "total": len(plan["requirements"]),
                                "satisfied": 0,
                                "requirements": plan["requirements"]}},
        )

    selections = []
    labels = []
    for item in satisfied:
        label = item["row"]["row_label"]
        if label in labels:
            continue
        labels.append(label)
        selections.append({
            "section_kind": plan["statement_kind"],
            "row_label": label, "column_header": column_header,
        })

    try:
        located = locate_cells_in_verified_pdf(
            entry.source, path, as_of=as_of, selections=selections,
            bounded_tables=True,
        )
    except ValueError as exc:
        return _withheld(
            report_key, str(exc) or "SOURCE_CELL_UNRESOLVED", document=document,
            extra={"request": {"question": question, "question_code": None},
                   "retrieval": retrieval_trace},
        )
    if len(located) != len(selections) or any(
        item.get("status") != "ONE_CELL_CANDIDATE" for item in located
    ):
        return _withheld(
            report_key, "SOURCE_CELL_UNRESOLVED", document=document,
            extra={"request": {"question": question, "question_code": None},
                   "retrieval": retrieval_trace},
        )

    verified: dict[str, tuple[dict, str]] = {}
    failures: dict[str, str] = {}
    with pymupdf.open(path) as pdf:
        for result, chosen in zip(located, selections):
            label = chosen["row_label"]
            options = result.get("candidates")
            if not isinstance(options, list) or len(options) != 1:
                failures[label] = "SOURCE_CELL_AMBIGUOUS"
                continue
            item = options[0]
            ok, reason = question_selection.validate_candidate(
                item, entry.source, section_kind=chosen["section_kind"],
                row_label=label, column_header=column_header,
            )
            if not ok:
                failures[label] = reason
                continue
            raw = str(item.get("cell_text_verbatim") or "").strip()
            if not raw:
                failures[label] = "SOURCE_CELL_BLANK_NOT_ZERO"
                continue
            if raw in {"-", "—", "–", "－", "―"}:
                failures[label] = "SOURCE_CELL_DASH_NOT_ZERO"
                continue
            accepted, rationale = revenue_scope.review_literal(item, pdf)
            if not accepted:
                failures[label] = "LITERAL_REVIEW_NOT_PASSED"
                continue
            verified[label] = (item, rationale)

    if not verified:
        return _withheld(
            report_key, "NO_VERIFIED_REQUIREMENT", document=document,
            extra={"request": {"question": question, "question_code": None},
                   "retrieval": retrieval_trace,
                   "coverage": {"complete": False, "total": len(plan["requirements"]),
                                "satisfied": 0, "requirements": plan["requirements"]}},
        )

    claims, reviews, observations = [], [], []
    for number, label in enumerate(labels, start=1):
        if label not in verified:
            continue
        item, rationale = verified[label]
        claim_id = f"Q{number}"
        claims.append(ResearchClaim(
            claim_id=claim_id, kind=ClaimKind.OBSERVED_FACT,
            text=(
                f'在「{item["statement_heading_verbatim"]}」中，'
                f'「{item["row_label_verbatim"]}」在'
                f'「{item["column_header_verbatim"]}」列披露为'
                f'「{item["cell_text_verbatim"]}」。'
            ),
            evidence_ids=(item["candidate_id"],),
        ))
        reviews.append(ClaimReview(
            claim_id=claim_id, reviewer_id="native-pdf-cell-literal-reviewer-v1",
            verdict=ReviewVerdict.ADMIT, rationale=rationale,
        ))
        observations.append({
            "claim_id": claim_id,
            "evidence_id": item["candidate_id"],
            "statement_title": item["statement_heading_verbatim"],
            "statement_type_candidate": item["section_kind_candidate"],
            "row_label": item["row_label_verbatim"],
            "column_header": item["column_header_verbatim"],
            "value_verbatim": item["cell_text_verbatim"],
            "statement_context": item["statement_context_verbatim"],
            "page_number": item["page_number"],
            "cell_bbox_pt": item["cell_bbox_pt"],
            "source_text_span_status": item["source_text_span_status"],
            "review_scope": "LITERAL_CELL_LOCATION_ONLY",
        })

    draft = {
        "status": "SOURCE_DRAFT_READY",
        "document_id": document.document_id,
        "source_sha256": document.source_sha256,
        "canonical_sha256": document.canonical_sha256,
        "source_url": document.source_url,
        "observations": observations,
        "claims": [claim.model_dump(mode="json") for claim in claims],
        "reviews": [review.model_dump(mode="json") for review in reviews],
    }
    decision = publication_policy.decide_publication(
        draft, document,
        expected_statement_kind=plan["statement_kind"],
        expected_row_labels=tuple(
            observation["row_label"] for observation in observations
        ),
        as_of=as_of,
    )
    if not decision.get("may_publish"):
        return _withheld(
            report_key, str(decision.get("reason") or "PUBLICATION_WITHHELD"),
            decision=decision, document=document,
            extra={"request": {"question": question, "question_code": None},
                   "retrieval": retrieval_trace},
        )

    published = set(decision["published_claim_ids"])
    draft_published = {
        "claims": [claim.model_dump(mode="json") for claim in claims
                   if claim.claim_id in published],
        "observations": [observation for observation in observations
                         if observation["claim_id"] in published],
    }
    facts = _fact_rows(draft_published, document)
    reviews_out = [{
        "claim_id": review.claim_id,
        "verdict": review.verdict.value,
        "reviewer_id": review.reviewer_id,
        "rationale": review.rationale,
        "review_scope": publication_policy.LITERAL_REVIEW_SCOPE,
    } for review in reviews if review.claim_id in published]

    requirement_rows = []
    covered = 0
    for item in plan["requirements"]:
        if item["status"] == "SATISFIED":
            label = item["row"]["row_label"]
            if label in verified:
                covered += 1
                requirement_rows.append({
                    "requirement_id": item["requirement_id"],
                    "facet": item["facet"], "status": "VERIFIED",
                    "row_label": label,
                })
            else:
                requirement_rows.append({
                    "requirement_id": item["requirement_id"],
                    "facet": item["facet"], "status": "NOT_VERIFIED",
                    "reason": failures.get(label, "VERIFICATION_FAILED"),
                })
        else:
            requirement_rows.append({
                "requirement_id": item["requirement_id"],
                "facet": item["facet"], "status": item["status"],
                "reason": item.get("status"),
            })

    coverage = {
        "complete": covered == len(plan["requirements"]),
        "total": len(plan["requirements"]),
        "satisfied": covered,
        "statement_kind": plan["statement_kind"],
        "selection_basis": plan["selection_basis"],
        "plan_source": plan.get("facets_source", "DETERMINISTIC_SPLIT"),
        "requirements": requirement_rows,
    }

    # Bounded repair: at most one optional clarification for the first missing
    # requirement. It never publishes on its own; the user confirms a verified
    # source row and the report is rebuilt with that row pinned.
    if (not coverage["complete"] and repair_secret and not pinned_rows):
        missing = next(
            (item for item in requirement_rows
             if item["status"] in {"NO_ROW_MATCH", "AMBIGUOUS"}),
            None,
        )
        if missing is not None:
            closed = clarification.closed_options(
                index, document, plan["statement_kind"],
            )
            candidates = clarification.near_match_options(closed, missing["facet"])
            if 1 <= len(candidates) <= 4:
                repair_token = clarification.sign_clarification(
                    question=question, document=document, report_key=report_key,
                    statement_kind=plan["statement_kind"],
                    option_ids=[option["option_id"] for option in candidates],
                    secret=repair_secret,
                    extra={"multi": True, "facet": missing["facet"]},
                )
                coverage["repair"] = {
                    "facet": missing["facet"],
                    "reason": "MISSING_REQUIREMENT_CANDIDATES",
                    "clarification_id": repair_token,
                    "options": [
                        {
                            "option_id": option["option_id"],
                            "row_label": option["row_label"],
                            "core": option["core"],
                        }
                        for option in candidates
                    ],
                }

    source = document.to_source_document()
    question_sha = sha256(question.encode("utf-8")).hexdigest()
    limitations = list(ASK_LIMITATIONS) + [
        "多条目问题只回答已满足并核验的条目；缺失项已列出，不做推断、比较或补写。",
    ]
    return {
        "status": "REPORT_READY",
        "reason": None,
        "report_type": "FACTS_ONLY_MULTI_REQUIREMENT_REPORT",
        "report_version": MULTI_VERSION,
        "report_key": report_key,
        "report_id": sha256(
            f"{document.document_id}|{document.canonical_sha256}|"
            f"{MULTI_VERSION}|{question_sha}".encode()
        ).hexdigest(),
        "issuer": {
            "name": document.issuer_name, "ticker": document.ticker,
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
        "request": {"question": question, "question_code": QUESTION_CODE},
        "intent": intent_block,
        "retrieval": _retrieval_trace(retrieval, include_excerpts=True),
        "selection": {
            "status": "SELECTION_READY",
            "statement_kind": plan["statement_kind"],
            "statement_title": document_index.SECTION_TITLES[plan["statement_kind"]],
            "column_header": column_header,
            "selection_basis": plan["selection_basis"],
            "rows": [item.get("row_label") for item in requirement_rows
                     if item["status"] == "VERIFIED"],
        },
        "coverage": coverage,
        "facts": facts,
        "reviews": reviews_out,
        "publication": decision,
        "limitations": limitations,
        "report_storage": "NOT_PERSISTED",
    }


MANAGEMENT_VERSION = "m5-management-evidence-preview-v1"


def _management_section_pages(path: Path) -> set[int]:
    """Pages of the management discussion section, if the document has one."""
    with pymupdf.open(path) as pdf:
        start = None
        for index in range(4, len(pdf) + 1):
            if "管理层讨论与分析" in pdf[index - 1].get_text("text"):
                start = index
                break
        if start is None:
            return set()
        end = None
        for index in range(start + 1, len(pdf) + 1):
            if re.search(r"第[一二三四五六七八九十]+节", pdf[index - 1].get_text("text")):
                end = index
                break
        return set(range(start, end or (start + 10)))


_QUESTION_STOPWORDS = (
    "为什么", "为何", "原因", "解释", "说明", "管理层讨论", "经营讨论",
    "变动原因", "什么原因", "如何解释", "怎么解释", "是什么", "多少",
    "如何", "怎么", "下降", "减少", "变动", "上升", "增加", "影响",
    "增长", "下滑", "由于", "主要系", "变化",
)


def _question_grams(question: str) -> set[str]:
    normalized = re.sub(r"\s+", "", unicodedata.normalize("NFKC", question))
    for word in _QUESTION_STOPWORDS:
        normalized = normalized.replace(word, "")
    generic = {
        "半年", "年度", "年半", "中航", "航沈", "沈飞", "公司", "报告",
        "期内", "本期", "情况", "人数",
    }
    grams = {normalized[index:index + 2] for index in range(len(normalized) - 1)}
    return {
        gram for gram in grams
        if not any(ch.isdigit() for ch in gram) and gram not in generic
    }


def _management_preview_pointers(path: Path, question: str) -> list[dict]:
    grams = _question_grams(question)
    section_pages = _management_section_pages(path)
    explanation_cues = ("下降", "减少", "变动", "原因", "主要系", "由于",
                        "增加", "上升", "影响", "下滑", "增长")
    candidates = []
    with pymupdf.open(path) as pdf:
        for page in sorted(section_pages):
            text = pdf[page - 1].get_text("text")
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            for index in range(len(lines)):
                line = lines[index]
                if (line.startswith(("√", "□", "-", "－"))
                        or sum("\u4e00" <= ch <= "\u9fff" for ch in line) < 6):
                    continue
                next_line = lines[index + 1] if index + 1 < len(lines) else None
                noisy_next = next_line is None or (
                    next_line.startswith(("√", "□", "-", "－"))
                    or sum("\u4e00" <= ch <= "\u9fff" for ch in next_line) < 2
                )
                if line.endswith(("。", "；", "：", "！", "？")) or noisy_next:
                    spans = (1,)
                else:
                    spans = (2,)
                first_compact = re.sub(
                    r"\s+", "", unicodedata.normalize("NFKC", line)
                )
                if (not any(gram in first_compact for gram in grams)
                        or not any(cue in first_compact for cue in explanation_cues)):
                    continue
                for span in spans:
                    excerpt = "\n".join(lines[index:index + span]).strip()
                    compact = re.sub(r"\s+", "", unicodedata.normalize("NFKC", excerpt))
                    if len(compact) < 16:
                        continue
                    metric_hits = sum(1 for gram in grams if gram in compact)
                    cue_hits = sum(1 for cue in explanation_cues if cue in compact)
                    if not metric_hits or not cue_hits:
                        continue
                    strong = any(
                        marker in compact
                        for marker in ("变动原因", "主要是", "主要系", "原因说明")
                    )
                    digits = sum(ch.isdigit() for ch in compact)
                    score = metric_hits * 2 + cue_hits * 3 - digits * 0.05
                    if strong:
                        score += 4
                    candidates.append((score, page, excerpt))

    candidates.sort(key=lambda item: (-item[0], item[1]))
    pointers = []
    seen = set()
    for _, page, excerpt in candidates:
        key = (page, re.sub(r"\s+", "", unicodedata.normalize("NFKC", excerpt))[-20:])
        if key in seen:
            continue
        seen.add(key)
        pointers.append({
            "page_number": page,
            "excerpt": excerpt[:240],
            "literal_check": "VERIFIED_PAGE_TEXT_SUBSTRING",
            "explanation_cue_present": True,
        })
        if len(pointers) == 3:
            break

    return pointers


def build_management_report(
    report_key: str,
    pdf_path: Path,
    question: str,
    *,
    as_of: datetime,
    review_secret: str | None = None,
) -> dict:
    """Management questions get an evidence preview that is never published.

    The excerpt is taken from a canonical text span bound to the manifest. It is
    a literal source preview only; management claims still require a semantic
    review that this platform does not perform.
    """
    entry = source_workspace.REPORTS.get(report_key)
    if entry is None or entry.authorization != source_workspace.AUTHORIZATION_MANIFEST:
        raise source_workspace.UnknownReportError("REPORT_NOT_AUTHORIZED_IN_CORPUS")

    document = corpus_manifest.load_corpus_manifest().require_report_key(report_key)
    if document.to_source_document() != entry.source:
        raise ValueError("MANIFEST_SOURCE_IDENTITY_MISMATCH")

    if (not isinstance(question, str) or not question.strip()
            or len(question) > MAX_QUESTION_CHARS):
        return _withheld(
            report_key, "QUESTION_INVALID", document=document,
            extra={"request": {"question": question, "question_code": None}},
        )

    path = Path(pdf_path)
    corpus_manifest.verify_document(document, pdf_path=path)

    intent = intent_gate.classify_intent(question)
    intent_block = {"value": intent.value, "version": intent_gate.INTENT_VERSION,
                    "rejection_reason": intent_gate.rejection_reason(intent)}
    if intent is not intent_gate.Intent.MANAGEMENT_EXPLANATION:
        return _withheld(
            report_key, "QUESTION_INTENT_AMBIGUOUS", document=document,
            extra={"request": {"question": question, "question_code": None},
                   "intent": intent_block},
        )

    try:
        retrieval = canonical_retrieval.retrieve_report_evidence(
            entry.source, path, question, as_of=as_of,
        )
    except ValueError as exc:
        return _withheld(
            report_key, str(exc) or "RETRIEVAL_FAILED", document=document,
            extra={"request": {"question": question, "question_code": None},
                   "intent": intent_block},
        )

    pointers = _management_preview_pointers(path, question)
    packet = None
    if review_secret and pointers:
        top = pointers[0]
        with pymupdf.open(path) as pdf:
            context_text = pdf[top["page_number"] - 1].get_text("text").strip()
        packet = semantic_review.build_packet(
            secret=review_secret, question=question, report_key=report_key,
            claim_type="MANAGEMENT_EXPLANATION", claim_text=top["excerpt"],
            page_number=top["page_number"], excerpt=top["excerpt"],
            context=context_text,
            document={
                "document_id": document.document_id,
                "source_sha256": document.source_sha256,
                "canonical_sha256": document.canonical_sha256,
            },
        )

    if not pointers:
        return _withheld(
            report_key, "NO_MANAGEMENT_EVIDENCE", document=document,
            extra={"request": {"question": question, "question_code": None},
                   "intent": intent_block},
        )

    source = document.to_source_document()
    question_sha = sha256(question.encode("utf-8")).hexdigest()
    limitations = [
        "管理层解释属于需语义审阅的声明；当前平台不发布这类声明，也不做语义审阅。",
        "摘录只是原文预览，用于定位来源，不构成已发布的结论。",
        "本报告不包含数字结论；数字事实请使用事实查询。",
    ]
    return {
        "status": "REPORT_WITHHELD",
        "reason": "MANAGEMENT_EXPLANATION_REQUIRES_SEMANTIC_REVIEW",
        "report_type": "MANAGEMENT_EVIDENCE_PREVIEW_REPORT",
        "report_version": MANAGEMENT_VERSION,
        "report_key": report_key,
        "report_id": sha256(
            f"{document.document_id}|{document.canonical_sha256}|"
            f"{MANAGEMENT_VERSION}|{question_sha}".encode()
        ).hexdigest(),
        "issuer": {
            "name": document.issuer_name, "ticker": document.ticker,
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
        "request": {"question": question, "question_code": QUESTION_CODE},
        "intent": intent_block,
        "retrieval": _retrieval_trace(retrieval),
        "facts": [],
        "management_preview": {
            "status": "PREVIEW_ONLY_NOT_PUBLISHED",
            "literal_check": "VERIFIED_CANONICAL_TEXT_SPAN_ONLY",
            "semantic_review": "NOT_PERFORMED",
            "pointers": pointers,
        },
        "review_packet": packet,
        "development_only": True,
        "independent_validation": False,
        "publication": {
            "may_publish": False,
            "reason": "MANAGEMENT_EXPLANATION_REQUIRES_SEMANTIC_REVIEW",
            "policy_version": publication_policy.POLICY_VERSION,
            "semantic_review": "NOT_PERFORMED",
        },
        "limitations": limitations,
        "report_storage": "NOT_PERSISTED",
    }


MIXED_VERSION = "m5-facts-with-management-preview-v1"
_SENTENCE_SPLIT = re.compile(r"[？?。；;\n]+")


def build_mixed_report(
    report_key: str,
    pdf_path: Path,
    question: str,
    *,
    as_of: datetime,
    review_secret: str | None = None,
) -> dict | None:
    """One question with a fact sentence and a management sentence.

    The fact part publishes through the normal path; the management part is
    attached as a withheld preview. Returns None when either part is absent or
    the fact part cannot publish, so the caller keeps the management-only path.
    """
    entry = source_workspace.REPORTS.get(report_key)
    if entry is None or entry.authorization != source_workspace.AUTHORIZATION_MANIFEST:
        raise source_workspace.UnknownReportError("REPORT_NOT_AUTHORIZED_IN_CORPUS")

    document = corpus_manifest.load_corpus_manifest().require_report_key(report_key)
    if document.to_source_document() != entry.source:
        raise ValueError("MANIFEST_SOURCE_IDENTITY_MISMATCH")

    if (not isinstance(question, str) or not question.strip()
            or len(question) > MAX_QUESTION_CHARS):
        return None

    fact_parts = []
    management_parts = []
    for part in _SENTENCE_SPLIT.split(question):
        part = part.strip()
        if len(part) < 2:
            continue
        sentence_intent = intent_gate.classify_intent(part)
        if sentence_intent is intent_gate.Intent.MANAGEMENT_EXPLANATION:
            management_parts.append(part)
        elif sentence_intent is intent_gate.Intent.FACT_LOOKUP:
            fact_parts.append(part)
    if not fact_parts or not management_parts:
        return None

    path = Path(pdf_path)
    fact_text = "，".join(fact_parts)
    try:
        fact_report = build_multi_report(report_key, path, fact_text, as_of=as_of)
        if fact_report is None:
            fact_report = build_report_from_question(report_key, path, fact_text, as_of=as_of)
    except (ValueError, source_workspace.UnknownReportError):
        return None
    if fact_report.get("status") != "REPORT_READY" or not fact_report.get("facts"):
        return None

    management_text = "，".join(management_parts)
    pointers = _management_preview_pointers(path, management_text)
    composed = dict(fact_report)
    composed["report_type"] = "FACTS_WITH_MANAGEMENT_PREVIEW_REPORT"
    composed["report_version"] = MIXED_VERSION
    composed["report_id"] = sha256(
        f"{document.document_id}|{document.canonical_sha256}|"
        f"{MIXED_VERSION}|{sha256(question.encode('utf-8')).hexdigest()}".encode()
    ).hexdigest()
    composed["management_preview"] = {
        "status": "PREVIEW_ONLY_NOT_PUBLISHED" if pointers else "NO_MANAGEMENT_EVIDENCE",
        "literal_check": "VERIFIED_PAGE_TEXT_SUBSTRING",
        "semantic_review": "NOT_PERFORMED",
        "pointers": pointers,
    }
    composed["management_publication"] = {
        "may_publish": False,
        "reason": "MANAGEMENT_EXPLANATION_REQUIRES_SEMANTIC_REVIEW",
        "semantic_review": "NOT_PERFORMED",
    }
    composed["review_packet"] = None
    if review_secret and pointers:
        top = pointers[0]
        with pymupdf.open(path) as pdf:
            context_text = pdf[top["page_number"] - 1].get_text("text").strip()
        composed["review_packet"] = semantic_review.build_packet(
            secret=review_secret, question=question, report_key=report_key,
            claim_type="MANAGEMENT_EXPLANATION", claim_text=top["excerpt"],
            page_number=top["page_number"], excerpt=top["excerpt"],
            context=context_text,
            document={
                "document_id": document.document_id,
                "source_sha256": document.source_sha256,
                "canonical_sha256": document.canonical_sha256,
            },
        )
    composed["development_only"] = True
    composed["independent_validation"] = False
    composed["limitations"] = list(composed.get("limitations") or []) + [
        "管理层解释部分只作原文预览，未发布；语义审阅未执行。",
        "已发布的事实只覆盖事实子句，不覆盖解释子句。",
    ]
    return composed
