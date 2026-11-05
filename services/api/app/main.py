import logging
import os
from functools import wraps
from threading import Lock

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.evidence import preview

app = FastAPI(
    title="Financial Research Platform API",
    version="0.1.0",
)


# Single-process local FastAPI safeguard: all PyMuPDF-consuming routes share
# one guard. Separate processes/workers remain out of scope.
_PDF_REQUEST_LOCK = Lock()


def _serialize_pdf_route(handler):
    @wraps(handler)  # Keep FastAPI's request/path parameter introspection.
    def guarded(*args, **kwargs):
        if not _PDF_REQUEST_LOCK.acquire(timeout=90):
            raise HTTPException(status_code=503, detail="SOURCE_UNAVAILABLE")
        try:
            return handler(*args, **kwargs)
        finally:
            _PDF_REQUEST_LOCK.release()
    return guarded


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "research-api",
    }


@app.get("/api/v1/research/evidence-preview/{document_id}")
@_serialize_pdf_route
def evidence_preview(document_id: str) -> dict:
    if os.environ.get("FRP_LOCAL_EVIDENCE_PREVIEW") != "1":
        raise HTTPException(status_code=404, detail="Evidence preview disabled")
    if document_id != preview.DOCUMENT_ID:
        raise HTTPException(status_code=404, detail="Document not available")
    try:
        return preview.build_source_preview(preview.PDF_PATH)
    except Exception:
        logging.getLogger(__name__).exception("Verified source preview unavailable")
        raise HTTPException(status_code=503, detail="SOURCE_UNAVAILABLE") from None


class SourceQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=240)


@app.post("/api/v1/research/ask")
@_serialize_pdf_route
def ask_source_question(request: SourceQuestion) -> dict:
    # Development-only, off by default; never expose unauthenticated in production.
    if os.environ.get("FRP_LOCAL_RESEARCH_QA") != "1":
        raise HTTPException(status_code=404, detail="Research Q&A disabled")
    from app.modules.financial_report_analyst import qa
    try:
        return qa.answer_question(request.question)
    except Exception:
        logging.getLogger(__name__).exception("Research Q&A source unavailable")
        raise HTTPException(status_code=503, detail="SOURCE_UNAVAILABLE") from None


@app.get("/api/v1/research/revenue-scope-preview")
@_serialize_pdf_route
def local_revenue_scope_preview() -> dict:
    """Explicitly local-only, opt-in, fail-closed source draft; no publication."""
    if os.environ.get("FRP_LOCAL_REVENUE_PREVIEW") != "1":
        raise HTTPException(status_code=404, detail="Revenue preview disabled")
    pdf_path = os.environ.get("FRP_LOCAL_REVENUE_PDF")
    if not pdf_path:
        raise HTTPException(status_code=503, detail="SOURCE_UNAVAILABLE")
    from datetime import datetime
    from pathlib import Path
    from zoneinfo import ZoneInfo
    from app.modules.financial_report_analyst import revenue_scope
    try:
        return revenue_scope.build_source_draft(
            revenue_scope.SOURCE,
            Path(pdf_path),
            as_of=datetime.now(ZoneInfo("Asia/Shanghai")),
        )
    except Exception:
        logging.getLogger(__name__).exception("Local revenue source draft unavailable")
        raise HTTPException(status_code=503, detail="SOURCE_UNAVAILABLE") from None


@app.get("/api/v1/research/source-workspace/{report_key}")
@_serialize_pdf_route
def local_source_workspace(report_key: str) -> dict:
    """Development-only source preview; report allowlist, no customer publication."""
    if os.environ.get("FRP_LOCAL_SOURCE_WORKSPACE") != "1":
        raise HTTPException(status_code=404, detail="Source workspace disabled")
    from datetime import datetime
    from pathlib import Path
    from zoneinfo import ZoneInfo
    from app.modules.financial_report_analyst import source_workspace

    entry = source_workspace.REPORTS.get(report_key)
    if entry is None:
        raise HTTPException(status_code=404, detail="Report not available")
    pdf_path = os.environ.get(entry.pdf_env_name)
    if not pdf_path:
        raise HTTPException(status_code=503, detail="SOURCE_UNAVAILABLE")
    try:
        return source_workspace.build_source_workspace(
            report_key, Path(pdf_path), as_of=datetime.now(ZoneInfo("Asia/Shanghai"))
        )
    except Exception:
        logging.getLogger(__name__).exception("Local source workspace unavailable")
        raise HTTPException(status_code=503, detail="SOURCE_UNAVAILABLE") from None

# M1.7B: explicitly local, authenticated single-shot model experiments.
# PDF parsing is separately serialized; the outbound LLM call never holds the
# PDF lock. One session has a hard budget of four attempts, including failures.
from typing import Literal
from hmac import compare_digest
from fastapi import Header
from pydantic import ConfigDict


class LocalRevenueQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_key: Literal["600276-2026H1", "600760-2026H1"]
    question_code: Literal["consolidated_revenue_2026H1", "revenue_rows_two_scopes_2026H1", "management_innovation_source_context_2026H1"]


_LOCAL_LLM_LIMIT = 4
_LOCAL_LLM_COUNT = 0
_LOCAL_LLM_LOCK = Lock()


@app.post("/api/v1/research/local-source-answer")
def local_source_answer(
    request: LocalRevenueQuestion,
    x_frp_local_token: str | None = Header(default=None),
) -> dict:
    """No arbitrary prompts/files, no public access, no automatic retries."""
    if (os.environ.get("FRP_LOCAL_LLM_UI") != "1"
        or os.environ.get("FRP_LOCAL_SOURCE_WORKSPACE") != "1"):
        raise HTTPException(status_code=404, detail="Local model experiment disabled")
    token = os.environ.get("FRP_LOCAL_LLM_ACCESS_TOKEN", "")
    if not token or not x_frp_local_token or not compare_digest(token, x_frp_local_token):
        raise HTTPException(status_code=404, detail="Not available")
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=503, detail="MODEL_NOT_CONFIGURED")
    from datetime import datetime
    from pathlib import Path
    from zoneinfo import ZoneInfo
    from app.modules.financial_report_analyst import source_workspace, workspace_llm, revenue_scope, multi_evidence, management_evidence, management_brief

    # Only Hengrui has an independently source-reviewed two-scope selection.
    if (request.question_code in (multi_evidence.QUESTION_CODE, management_brief.QUESTION_CODE)
        and request.report_key != "600276-2026H1"):
        raise HTTPException(status_code=422, detail="UNSUPPORTED_REPORT_QUESTION_PAIR")

    entry = source_workspace.REPORTS.get(request.report_key)
    if entry is None:
        raise HTTPException(status_code=404, detail="Report not available")
    pdf_path = os.environ.get(entry.pdf_env_name)
    if not pdf_path:
        raise HTTPException(status_code=503, detail="SOURCE_UNAVAILABLE")
    if not _LOCAL_LLM_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="MODEL_REQUEST_IN_PROGRESS")
    global _LOCAL_LLM_COUNT
    try:
        if _LOCAL_LLM_COUNT >= _LOCAL_LLM_LIMIT:
            raise HTTPException(status_code=429, detail="LOCAL_MODEL_CALL_LIMIT_REACHED")
        management_passage = None
        if not _PDF_REQUEST_LOCK.acquire(timeout=90):
            raise HTTPException(status_code=503, detail="SOURCE_UNAVAILABLE")
        try:
            try:
                as_of = datetime.now(ZoneInfo("Asia/Shanghai"))
                if request.question_code in (multi_evidence.QUESTION_CODE, management_brief.QUESTION_CODE):
                    source_draft = revenue_scope.build_source_draft(
                        revenue_scope.SOURCE, Path(pdf_path), as_of=as_of,
                    )
                    if (request.question_code == management_brief.QUESTION_CODE
                        and source_draft.get("status") == "SOURCE_DRAFT_READY"):
                        management_passage = management_evidence.locate_management_excerpt(
                            Path(pdf_path), as_of=as_of,
                        )
                else:
                    source_draft = source_workspace.build_source_workspace(
                        request.report_key, Path(pdf_path), as_of=as_of,
                    )
            except Exception:
                # Never log document text, provider responses, or credentials.
                raise HTTPException(status_code=503, detail="SOURCE_UNAVAILABLE") from None
        finally:
            _PDF_REQUEST_LOCK.release()
        if source_draft.get("status") != "SOURCE_DRAFT_READY":
            return {"status": "WITHHELD", "reason": "SOURCE_NOT_QUALIFIED",
                    "claims": [], "research_publication": "BLOCKED",
                    "financial_semantic_review": "NOT_PERFORMED"}
        _LOCAL_LLM_COUNT += 1  # Debit even if DeepSeek fails; never retry.
        if request.question_code == management_brief.QUESTION_CODE:
            return management_brief.draft_management_brief(
                source_draft, management_passage, api_key=api_key,
            )
        if request.question_code == multi_evidence.QUESTION_CODE:
            return multi_evidence.draft_two_source_brief(
                source_draft, api_key=api_key,
            )
        return workspace_llm.draft_one_source_answer(
            request.report_key, source_draft, api_key=api_key,
        )
    finally:
        _LOCAL_LLM_LOCK.release()


# M1.9C: local-only claim review; no paid provider or publication.
class LocalClaimReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_key: Literal["600276-2026H1"]
    claim_code: Literal[
        "share_drug_sales",
        "share_company_revenue",
        "growth_innovative_drugs",
        "growth_company_revenue",
    ]


@app.post("/api/v1/research/local-claim-review")
@_serialize_pdf_route
def local_claim_review(
    request: LocalClaimReviewRequest,
    x_frp_local_token: str | None = Header(default=None),
) -> dict:
    if os.environ.get("FRP_LOCAL_CLAIM_REVIEW_UI") != "1":
        raise HTTPException(status_code=404, detail="Not available")

    token = os.environ.get("FRP_LOCAL_LLM_ACCESS_TOKEN", "")
    if (
        len(token) < 32
        or not x_frp_local_token
        or not compare_digest(token, x_frp_local_token)
    ):
        raise HTTPException(status_code=404, detail="Not available")

    pdf_path = os.environ.get("FRP_LOCAL_REVENUE_PDF")
    if not pdf_path:
        raise HTTPException(status_code=503, detail="SOURCE_UNAVAILABLE")

    from datetime import datetime
    from pathlib import Path
    from zoneinfo import ZoneInfo

    from app.modules.financial_report_analyst.claim_review_preview import (
        build_preview,
    )

    try:
        return build_preview(
            Path(pdf_path),
            request.claim_code,
            as_of=datetime.now(ZoneInfo("Asia/Shanghai")),
        )
    except Exception:
        # Never expose PDF text, paths, secrets, or exception contents.
        raise HTTPException(
            status_code=503,
            detail="SOURCE_UNAVAILABLE",
        ) from None


# M1.10B: manual Analyst candidate, independently reviewed; no model call.
class LocalAnalystDraftReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_key: Literal["600276-2026H1"]
    candidate_text: str = Field(min_length=1, max_length=400)


@app.post("/api/v1/research/local-analyst-draft-review")
@_serialize_pdf_route
def local_analyst_draft_review(
    request: LocalAnalystDraftReviewRequest,
    x_frp_local_token: str | None = Header(default=None),
) -> dict:
    if os.environ.get("FRP_LOCAL_ANALYST_REVIEW_UI") != "1":
        raise HTTPException(status_code=404, detail="Not available")

    token = os.environ.get("FRP_LOCAL_LLM_ACCESS_TOKEN", "")
    if (
        len(token) < 32
        or not x_frp_local_token
        or not compare_digest(token, x_frp_local_token)
    ):
        raise HTTPException(status_code=404, detail="Not available")

    pdf_path = os.environ.get("FRP_LOCAL_REVENUE_PDF")
    if not pdf_path:
        raise HTTPException(status_code=503, detail="SOURCE_UNAVAILABLE")

    from datetime import datetime
    from pathlib import Path
    from zoneinfo import ZoneInfo
    from app.modules.financial_report_analyst.analyst_claim_review import (
        review_analyst_draft,
    )

    try:
        return review_analyst_draft(
            Path(pdf_path),
            request.candidate_text,
            as_of=datetime.now(ZoneInfo("Asia/Shanghai")),
        )
    except Exception:
        # Fail closed. No raw exceptions, PDF contents or secrets.
        raise HTTPException(
            status_code=503, detail="SOURCE_UNAVAILABLE"
        ) from None


# M112B: one local-only source report preview. No model or publication.
class LocalSourceReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_key: Literal["600276-2026H1"]
    answer_kind: Literal[
        "CONSOLIDATED_REVENUE", "INNOVATIVE_SHARE_OF_DRUG_SALES",
    ] | None = None


@app.post("/api/v1/research/local-source-report")
@_serialize_pdf_route
def local_source_report(
    request: LocalSourceReportRequest,
    x_frp_local_token: str | None = Header(default=None),
) -> dict:
    if os.environ.get("FRP_LOCAL_REPORT_PREVIEW_UI") != "1":
        raise HTTPException(status_code=404, detail="Not available")

    token = os.environ.get("FRP_LOCAL_LLM_ACCESS_TOKEN", "")
    if (
        len(token) < 32
        or not x_frp_local_token
        or not compare_digest(token, x_frp_local_token)
    ):
        raise HTTPException(status_code=404, detail="Not available")

    pdf_path = os.environ.get("FRP_LOCAL_REVENUE_PDF")
    if not pdf_path:
        raise HTTPException(status_code=503, detail="SOURCE_UNAVAILABLE")

    from datetime import datetime
    from pathlib import Path
    from zoneinfo import ZoneInfo
    from app.modules.financial_report_analyst.source_report_preview import (
        build_source_report,
    )

    try:
        result = build_source_report(
            Path(pdf_path),
            as_of=datetime.now(ZoneInfo("Asia/Shanghai")),
        )
        if (
            result.get("status") != "LOCAL_SOURCE_REPORT_READY"
            or result.get("research_publication") != "BLOCKED"
            or result.get("financial_semantic_review") != "NOT_PERFORMED"
            or result.get("report_storage") != "NOT_PERSISTED"
        ):
            raise ValueError("REPORT_GATE_FAILED")
        if request.answer_kind is not None:
            from app.modules.financial_report_analyst.source_evidence_router import (
                route_evidence,
            )
            result["routed_evidence"] = route_evidence(result, request.answer_kind)
        return result
    except Exception:
        raise HTTPException(
            status_code=503, detail="SOURCE_UNAVAILABLE"
        ) from None


# M119A: local-only DeepSeek question interpretation. No source publication.
class LocalQuestionIntentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_key: Literal["600276-2026H1"]
    question: str = Field(min_length=1, max_length=240)


_M119A_INTENT_LIMIT = 4
_M119A_INTENT_COUNT = 0
_M119A_INTENT_LOCK = Lock()


@app.post("/api/v1/research/local-question-intent")
def local_question_intent(
    request: LocalQuestionIntentRequest,
    x_frp_local_token: str | None = Header(default=None),
) -> dict:
    if os.environ.get("FRP_LOCAL_QUESTION_INTENT_UI") != "1":
        raise HTTPException(status_code=404, detail="Not available")

    token = os.environ.get("FRP_LOCAL_LLM_ACCESS_TOKEN", "")
    if (
        len(token) < 32
        or not x_frp_local_token
        or not compare_digest(token, x_frp_local_token)
    ):
        raise HTTPException(status_code=404, detail="Not available")

    from app.modules.financial_report_analyst import live_question_intent

    # Reject unsupported intent before consuming any paid request budget.
    if not live_question_intent.in_current_source_scope(request.question):
        return live_question_intent._withheld(
            "QUESTION_OUTSIDE_SUPPORTED_SCOPE"
        )

    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=503, detail="MODEL_NOT_CONFIGURED")
    if not _M119A_INTENT_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="MODEL_REQUEST_IN_PROGRESS")

    global _M119A_INTENT_COUNT
    try:
        if _M119A_INTENT_COUNT >= _M119A_INTENT_LIMIT:
            raise HTTPException(
                status_code=429, detail="LOCAL_MODEL_CALL_LIMIT_REACHED"
            )
        _M119A_INTENT_COUNT += 1  # Failures cost budget; no retries.
        return live_question_intent.propose(
            request.question, api_key=api_key,
        )
    finally:
        _M119A_INTENT_LOCK.release()

# M122: local-only source-bound lexical retrieval preview (no model, no GT).
class LocalEvidenceSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_key: Literal["600276-2026H1"]
    question: str = Field(min_length=1, max_length=240)


@app.post("/api/v1/research/local-evidence-search")
@_serialize_pdf_route
def local_evidence_search(
    request: LocalEvidenceSearchRequest,
    x_frp_local_token: str | None = Header(default=None),
) -> dict:
    if os.environ.get("FRP_LOCAL_RETRIEVAL_UI") != "1":
        raise HTTPException(status_code=404, detail="Not available")

    token = os.environ.get("FRP_LOCAL_LLM_ACCESS_TOKEN", "")
    if (len(token) < 32 or not x_frp_local_token
        or not compare_digest(token, x_frp_local_token)):
        raise HTTPException(status_code=404, detail="Not available")

    pdf_path = os.environ.get("FRP_LOCAL_REVENUE_PDF")
    if not pdf_path:
        raise HTTPException(status_code=503, detail="SOURCE_UNAVAILABLE")

    from datetime import datetime
    from pathlib import Path
    from zoneinfo import ZoneInfo
    from app.modules.financial_report_analyst import canonical_retrieval, revenue_scope

    try:
        return canonical_retrieval.retrieve_report_evidence(
            revenue_scope.SOURCE, Path(pdf_path), request.question,
            as_of=datetime.now(ZoneInfo("Asia/Shanghai")),
        )
    except Exception:
        # Never log document text, source paths, model credentials or request data.
        raise HTTPException(status_code=503, detail="SOURCE_UNAVAILABLE") from None

# M124: explicitly local, unpublished retrieval-grounded Analyst preview.
class LocalRetrievalAnalystRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    report_key: Literal["600276-2026H1"]
    question: str = Field(min_length=1, max_length=240)


_M124_MODEL_CALL_LIMIT = 3
_M124_MODEL_CALL_COUNT = 0
_M124_MODEL_LOCK = Lock()


@app.post("/api/v1/research/local-retrieval-analyst")
@_serialize_pdf_route
def local_retrieval_analyst(
    request: LocalRetrievalAnalystRequest,
    x_frp_local_token: str | None = Header(default=None),
) -> dict:
    if os.environ.get("FRP_LOCAL_ANALYST_PREVIEW_UI") != "1":
        raise HTTPException(status_code=404, detail="Not available")
    token = os.environ.get("FRP_LOCAL_LLM_ACCESS_TOKEN", "")
    if (len(token) < 32 or not x_frp_local_token or
            not compare_digest(token, x_frp_local_token)):
        raise HTTPException(status_code=404, detail="Not available")
    source_pdf = os.environ.get("FRP_LOCAL_REVENUE_PDF")
    if not source_pdf:
        raise HTTPException(status_code=503, detail="SOURCE_UNAVAILABLE")
    from datetime import datetime
    from pathlib import Path
    from zoneinfo import ZoneInfo
    from app.modules.financial_report_analyst import (
        canonical_retrieval, retrieval_analyst, revenue_scope,
    )
    try:
        as_of = datetime.now(ZoneInfo("Asia/Shanghai"))
        packet = canonical_retrieval.retrieve_report_evidence(
            revenue_scope.SOURCE, Path(source_pdf), request.question, as_of=as_of,
        )
    except Exception:
        raise HTTPException(status_code=503, detail="SOURCE_UNAVAILABLE") from None
    # Check evidence and statement-scope gates without consuming model budget.
    try:
        retrieval_analyst._validated_evidence(
            revenue_scope.SOURCE, packet, request.question, as_of,
        )
    except (ValueError, TypeError, KeyError, AttributeError):
        return retrieval_analyst._withheld("EVIDENCE_OR_SCOPE_NOT_QUALIFIED", packet)
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        return retrieval_analyst._withheld("MODEL_NOT_CONFIGURED", packet)
    if not _M124_MODEL_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="MODEL_REQUEST_IN_PROGRESS")
    global _M124_MODEL_CALL_COUNT
    try:
        if _M124_MODEL_CALL_COUNT >= _M124_MODEL_CALL_LIMIT:
            raise HTTPException(status_code=429, detail="LOCAL_MODEL_CALL_LIMIT_REACHED")
        _M124_MODEL_CALL_COUNT += 1  # Charge the one-call budget before contacting provider.
        return retrieval_analyst.draft_from_verified_retrieval(
            revenue_scope.SOURCE, packet, request.question,
            as_of=as_of, api_key=api_key,
        )
    finally:
        _M124_MODEL_LOCK.release()


# M1: one local, dev-only facts-only disclosure report. No persistence, no
# model, and no production exposure. Publication is decided by
# publication_policy from the verified draft, not by this route.
class LocalFactsQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=2, max_length=240)


def _require_facts_report_access(report_key: str, token: str | None) -> None:
    """Shared dev-only gate: production refusal, feature flag, local secret."""
    if os.environ.get("FRP_ENV", "").strip().casefold() in {
        "production", "prod", "staging",
    }:
        raise HTTPException(status_code=404, detail="Not available")
    if os.environ.get("FRP_LOCAL_FACTS_REPORT") != "1":
        raise HTTPException(status_code=404, detail="Not available")
    expected = os.environ.get("FRP_LOCAL_LLM_ACCESS_TOKEN", "")
    if (len(expected) < 32 or not token
            or not compare_digest(expected, token)):
        raise HTTPException(status_code=404, detail="Not available")
    from app.modules.financial_report_analyst import report_builder
    if report_key not in report_builder.supported_report_keys():
        raise HTTPException(status_code=404, detail="Report not available")


def _facts_report_pdf_path(report_key: str) -> str:
    pdf_path = os.environ.get(f"FRP_LOCAL_SOURCE_PDF_{report_key.split('-')[0]}")
    if not pdf_path:
        raise HTTPException(status_code=503, detail="SOURCE_UNAVAILABLE")
    return pdf_path


@app.get("/api/v1/research/reports/{report_key}")
@_serialize_pdf_route
def local_facts_report(
    report_key: str,
    x_frp_local_token: str | None = Header(default=None),
) -> dict:
    """Dev-only facts-only report; the shared local secret is the gate."""
    _require_facts_report_access(report_key, x_frp_local_token)
    pdf_path = _facts_report_pdf_path(report_key)

    from datetime import datetime
    from pathlib import Path
    from zoneinfo import ZoneInfo
    from app.modules.financial_report_analyst import report_builder

    try:
        return report_builder.build_report(
            report_key, Path(pdf_path),
            as_of=datetime.now(ZoneInfo("Asia/Shanghai")),
        )
    except Exception:
        logging.getLogger(__name__).exception("Facts-only report unavailable")
        raise HTTPException(status_code=503, detail="SOURCE_UNAVAILABLE") from None


_M3_CLARIFY_LLM_LIMIT = 4
_M3_CLARIFY_LLM_COUNT = 0
_M3_CLARIFY_LLM_LOCK = Lock()

_M4_PLAN_LLM_LIMIT = 4
_M4_PLAN_LLM_COUNT = 0
_M4_PLAN_LLM_LOCK = Lock()


def _attempt_scope_clarification(
    report_key: str, question: str, present_kinds: list[str],
) -> dict | None:
    """Ask which statement the question means; options are statement titles."""
    from app.evidence import corpus_manifest
    from app.modules.financial_report_analyst import clarification

    document = corpus_manifest.load_corpus_manifest().require_report_key(report_key)
    secret = clarification._secret(
        os.environ.get("FRP_LOCAL_LLM_ACCESS_TOKEN", "")
    )
    return clarification.build_scope_clarification(
        report_key=report_key, document=document,
        present_kinds=present_kinds, question=question, secret=secret,
    )


def _attempt_clarification(
    report_key: str,
    pdf_path: str,
    question: str,
    *,
    statement_kind: str,
    as_of,
) -> dict | None:
    """Metric-identity clarification, with an opt-in, budgeted LLM proposal."""
    from pathlib import Path
    from app.evidence import corpus_manifest, document_index
    from app.modules.financial_report_analyst import (
        clarification, interpretation, question_selection, source_workspace,
    )

    document = corpus_manifest.load_corpus_manifest().require_report_key(report_key)
    entry = source_workspace.REPORTS[report_key]
    try:
        index = document_index.index_document_scoped(
            entry.source, Path(pdf_path), as_of=as_of,
            section_kinds=frozenset(question_selection.INCOME_STATEMENT_KINDS),
        )
    except Exception:
        return None

    closed = clarification.closed_options(index, document, statement_kind)

    proposed_ids: list[str] | None = None
    rationale: str | None = None
    interpretation_status: str | None = None
    interpretation_reason: str | None = None
    if os.environ.get("FRP_LOCAL_CLARIFY_LLM") == "1":
        api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if api_key:
            global _M3_CLARIFY_LLM_COUNT
            if _M3_CLARIFY_LLM_LOCK.acquire(blocking=False):
                try:
                    if _M3_CLARIFY_LLM_COUNT < _M3_CLARIFY_LLM_LIMIT:
                        _M3_CLARIFY_LLM_COUNT += 1
                        interp = interpretation.interpret(
                            question, closed, api_key=api_key,
                        )
                        if interp.get("status") == "INTERPRETATION_READY":
                            proposed_ids = interp["candidate_option_ids"]
                            rationale = interp["rationale"]
                            interpretation_status = "UNVERIFIED_PROPOSAL"
                        else:
                            interpretation_status = "WITHHELD"
                            interpretation_reason = interp.get("reason")
                finally:
                    _M3_CLARIFY_LLM_LOCK.release()

    secret = clarification._secret(
        os.environ.get("FRP_LOCAL_LLM_ACCESS_TOKEN", "")
    )
    return clarification.build_clarification(
        report_key=report_key, document=document, index=index, question=question,
        statement_kind=statement_kind, secret=secret,
        proposed_option_ids=proposed_ids, interpretation_rationale=rationale,
        interpretation_status=interpretation_status,
        interpretation_reason=interpretation_reason,
    )


class LocalClarificationResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=2, max_length=240)
    clarification_id: str = Field(min_length=16, max_length=4096)
    option_id: str = Field(min_length=32, max_length=128)


@app.post("/api/v1/research/reports/{report_key}/ask")
@_serialize_pdf_route
def local_facts_report_ask(
    report_key: str,
    request: LocalFactsQuestion,
    x_frp_local_token: str | None = Header(default=None),
) -> dict:
    """M2a/M3: dev-only question -> retrieval -> verified cells -> policy."""
    _require_facts_report_access(report_key, x_frp_local_token)
    pdf_path = _facts_report_pdf_path(report_key)

    from datetime import datetime
    from hashlib import sha256
    from pathlib import Path
    from zoneinfo import ZoneInfo
    from app.modules.financial_report_analyst import evidence_plan, report_builder

    as_of = datetime.now(ZoneInfo("Asia/Shanghai"))
    repair_secret = sha256(
        os.environ.get("FRP_LOCAL_LLM_ACCESS_TOKEN", "").encode("utf-8")
    ).hexdigest()
    try:
        plan_api_key = None
        if os.environ.get("FRP_LOCAL_CLARIFY_LLM") == "1":
            key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
            if key and _M4_PLAN_LLM_LOCK.acquire(blocking=False):
                try:
                    limit = int(os.environ.get("FRP_LOCAL_PLAN_LLM_LIMIT", "4"))
                    global _M4_PLAN_LLM_COUNT
                    if _M4_PLAN_LLM_COUNT < limit:
                        _M4_PLAN_LLM_COUNT += 1
                        plan_api_key = key
                finally:
                    _M4_PLAN_LLM_LOCK.release()
        if (report_builder.intent_gate.classify_intent(request.question)
                is report_builder.intent_gate.Intent.MANAGEMENT_EXPLANATION):
            result = report_builder.build_mixed_report(
                report_key, Path(pdf_path), request.question, as_of=as_of,
            )
            if result is None:
                result = report_builder.build_management_report(
                    report_key, Path(pdf_path), request.question, as_of=as_of,
                )
        elif len(evidence_plan.split_facets(request.question)) >= 2 or plan_api_key:
            result = report_builder.build_multi_report(
                report_key, Path(pdf_path), request.question, as_of=as_of,
                repair_secret=repair_secret, api_key=plan_api_key,
            )
            if result is None:
                result = report_builder.build_report_from_question(
                    report_key, Path(pdf_path), request.question, as_of=as_of,
                )
        else:
            result = report_builder.build_report_from_question(
                report_key, Path(pdf_path), request.question, as_of=as_of,
            )
    except Exception:
        logging.getLogger(__name__).exception("Question report unavailable")
        raise HTTPException(status_code=503, detail="SOURCE_UNAVAILABLE") from None

    if result.get("status") == "REPORT_WITHHELD":
        trace = (result.get("selection") or {}).get("trace") or {}
        if result.get("reason") == "NO_ROW_MATCH":
            statement_kind = trace.get("statement_kind")
            if statement_kind:
                clarification = _attempt_clarification(
                    report_key, pdf_path, request.question,
                    statement_kind=statement_kind, as_of=as_of,
                )
                if clarification is not None:
                    return clarification
        elif result.get("reason") == "AMBIGUOUS_STATEMENT_SCOPE":
            present = trace.get("present_statement_kinds") or []
            compact = "".join(request.question.split())
            titles = [
                document_index_title for document_index_title in (
                    "合并利润表", "母公司利润表",
                ) if document_index_title in compact
            ]
            if not titles and present:
                scope = _attempt_scope_clarification(
                    report_key, request.question, present,
                )
                if scope is not None:
                    return scope
    return result


@app.post("/api/v1/research/reports/{report_key}/ask/resolve")
@_serialize_pdf_route
def local_facts_report_resolve(
    report_key: str,
    request: LocalClarificationResolveRequest,
    x_frp_local_token: str | None = Header(default=None),
) -> dict:
    """Resume a clarification: the chosen option is re-verified, never trusted."""
    _require_facts_report_access(report_key, x_frp_local_token)
    pdf_path = _facts_report_pdf_path(report_key)

    from datetime import datetime
    from hashlib import sha256
    from pathlib import Path
    from zoneinfo import ZoneInfo
    from app.evidence import corpus_manifest, document_index
    from app.modules.financial_report_analyst import (
        clarification, question_selection, report_builder, source_workspace,
    )

    document = corpus_manifest.load_corpus_manifest().require_report_key(report_key)
    entry = source_workspace.REPORTS[report_key]
    secret = clarification._secret(
        os.environ.get("FRP_LOCAL_LLM_ACCESS_TOKEN", "")
    )
    try:
        payload = clarification.verify_clarification(request.clarification_id, secret)
    except ValueError:
        raise HTTPException(status_code=422, detail="Clarification unavailable") from None

    if (payload.get("document_id") != document.document_id
            or payload.get("canonical_sha256") != document.canonical_sha256
            or payload.get("question_sha256")
                != sha256(request.question.encode("utf-8")).hexdigest()
            or request.option_id not in payload.get("option_ids", [])):
        raise HTTPException(status_code=422, detail="Clarification unavailable")

    try:
        index = document_index.index_document_scoped(
            entry.source, Path(pdf_path),
            as_of=datetime.now(ZoneInfo("Asia/Shanghai")),
            section_kinds=frozenset(question_selection.INCOME_STATEMENT_KINDS),
        )
    except Exception:
        raise HTTPException(status_code=503, detail="SOURCE_UNAVAILABLE") from None

    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    if payload.get("kind") == "STATEMENT_SCOPE":
        present = {
            section["section_kind"] for section in index.get("sections", [])
            if section.get("section_kind") in question_selection.INCOME_STATEMENT_KINDS
        }
        chosen = next(
            (kind for kind in present
             if clarification.scope_option_id(document, kind) == request.option_id),
            None,
        )
        if chosen is None:
            raise HTTPException(status_code=422, detail="Clarification unavailable")
        try:
            return report_builder.build_report_from_question(
                report_key, Path(pdf_path), request.question, as_of=now,
                forced_statement_kind=chosen,
            )
        except Exception:
            logging.getLogger(__name__).exception("Resolve report unavailable")
            raise HTTPException(status_code=503, detail="SOURCE_UNAVAILABLE") from None

    closed = clarification.closed_options(index, document, payload["statement_kind"])
    option = next((o for o in closed if o["option_id"] == request.option_id), None)
    if option is None:
        raise HTTPException(status_code=422, detail="Clarification unavailable")

    if payload.get("multi") and payload.get("facet"):
        try:
            repaired = report_builder.build_multi_report(
                report_key, Path(pdf_path), request.question, as_of=now,
                pinned_rows={payload["facet"]: option["row_label"]},
                repair_secret=None,
            )
        except Exception:
            logging.getLogger(__name__).exception("Repair report unavailable")
            raise HTTPException(status_code=503, detail="SOURCE_UNAVAILABLE") from None
        if repaired is None:
            raise HTTPException(status_code=422, detail="Clarification unavailable")
        return repaired

    try:
        return report_builder.build_report_from_question(
            report_key, Path(pdf_path), request.question, as_of=now,
            forced_selection={
                "statement_kind": option["statement_kind"],
                "row_label": option["row_label"],
                "core": option["core"],
            },
        )
    except Exception:
        logging.getLogger(__name__).exception("Resolve report unavailable")
        raise HTTPException(status_code=503, detail="SOURCE_UNAVAILABLE") from None
