import logging
import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.evidence import preview

app = FastAPI(
    title="Financial Research Platform API",
    version="0.1.0",
)


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "research-api",
    }


@app.get("/api/v1/research/evidence-preview/{document_id}")
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
