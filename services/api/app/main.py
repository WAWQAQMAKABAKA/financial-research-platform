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
