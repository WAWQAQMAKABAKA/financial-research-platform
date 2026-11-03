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
    intent_gate,
    publication_policy,
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
) -> dict:
    """Question -> retrieval -> statement rows -> verified cells -> policy.

    The question selects *which* rows are cited; it never decides whether they
    are true. Every citation is re-located in the native PDF and re-checked by
    the literal reviewer before the policy may publish it.
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

    selection = question_selection.select_cells(
        index, question=question, report_period=document.report_period,
        column_header=column_header, retrieval_hits=retrieval_trace["hits"],
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
