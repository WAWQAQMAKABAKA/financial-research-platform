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
