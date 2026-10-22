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
    question_code: Literal["consolidated_revenue_2026H1"]


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
    from app.modules.financial_report_analyst import source_workspace, workspace_llm

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
        if not _PDF_REQUEST_LOCK.acquire(timeout=90):
            raise HTTPException(status_code=503, detail="SOURCE_UNAVAILABLE")
        try:
            try:
                source_draft = source_workspace.build_source_workspace(
                    request.report_key, Path(pdf_path),
                    as_of=datetime.now(ZoneInfo("Asia/Shanghai")),
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
        return workspace_llm.draft_one_source_answer(
            request.report_key, source_draft, api_key=api_key,
        )
    finally:
        _LOCAL_LLM_LOCK.release()
