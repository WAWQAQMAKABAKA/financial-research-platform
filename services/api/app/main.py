import logging
import os

from fastapi import FastAPI, HTTPException

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
