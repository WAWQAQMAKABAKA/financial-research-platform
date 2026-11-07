"""Semantic-review packet and development-only review records (M5.1).

The packet pauses publication: it carries one management-explanation claim, its
evidence and a fixed checklist. A review is recorded only from an explicit
verdict supplied by an allowlisted reviewer. Nothing here decides on its own.

Reviews are development-only. They are not independent validation and must not be
presented as such.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from hashlib import sha256
import hmac
import json
import os
from pathlib import Path
import time

PACKET_VERSION = "frp-semantic-review-packet-v1"
REVIEW_VERSION = "frp-semantic-review-v1"
REVIEW_TTL_SECONDS = int(os.environ.get("FRP_SEMANTIC_REVIEW_TTL", "900"))

CHECKLIST_KEYS = (
    "metric_identity",
    "period",
    "entity",
    "basis",
    "evidence_support",
    "no_overreach",
)
CHECKLIST_LABELS = {
    "metric_identity": "指标身份一致（同一指标，不是相近指标）",
    "period": "期间一致",
    "entity": "主体一致",
    "basis": "口径/合并范围一致",
    "evidence_support": "原文确实支持该表述",
    "no_overreach": "是否没有增加原文之外的断言？",
}
VERDICTS = ("ADMIT", "REJECT", "UNCERTAIN")
DEFAULT_REVIEWER = "local-reviewer"
MAX_TOKEN_CHARS = 8192
MAX_RATIONALE_CHARS = 2000


def reviewers_from_env() -> tuple[str, ...]:
    raw = os.environ.get("FRP_SEMANTIC_REVIEWERS", DEFAULT_REVIEWER)
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _sign(payload: dict, secret: str) -> str:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), body, sha256).hexdigest()
    return f"{_b64(body)}.{signature}"


def _verify(token: str, secret: str) -> dict:
    if not isinstance(token, str) or not token or len(token) > MAX_TOKEN_CHARS:
        raise ValueError("REVIEW_PACKET_INVALID")
    try:
        encoded, signature = token.split(".", 1)
        body = _unb64(encoded)
    except (ValueError, TypeError):
        raise ValueError("REVIEW_PACKET_INVALID") from None
    expected = hmac.new(secret.encode("utf-8"), body, sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise ValueError("REVIEW_PACKET_SIGNATURE_INVALID")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("REVIEW_PACKET_INVALID") from None
    if not isinstance(payload, dict) or payload.get("kind") != "SEMANTIC_REVIEW":
        raise ValueError("REVIEW_PACKET_INVALID")
    if payload.get("packet_version") != PACKET_VERSION:
        raise ValueError("REVIEW_PACKET_INVALID")
    if int(payload.get("expires_at", 0)) <= int(time.time()):
        raise ValueError("REVIEW_PACKET_EXPIRED")
    return payload


def build_packet(
    *,
    secret: str,
    question: str,
    report_key: str,
    claim_type: str,
    claim_text: str,
    page_number: int,
    excerpt: str,
    document: dict,
    context: str | None = None,
) -> dict:
    if not isinstance(claim_text, str) or not claim_text.strip():
        raise ValueError("REVIEW_CLAIM_INVALID")
    now = int(time.time())
    payload = {
        "kind": "SEMANTIC_REVIEW",
        "packet_version": PACKET_VERSION,
        "report_key": report_key,
        "question": question,
        "question_sha256": sha256(question.encode("utf-8")).hexdigest(),
        "claim_type": claim_type,
        "claim_text": claim_text.strip(),
        "page_number": int(page_number),
        "excerpt_sha256": sha256(excerpt.encode("utf-8")).hexdigest(),
        "excerpt": excerpt,
        "context": (context or "").strip(),
        "context_sha256": (
            sha256((context or "").strip().encode("utf-8")).hexdigest()
            if (context or "").strip() else None
        ),
        "document_id": document["document_id"],
        "source_sha256": document["source_sha256"],
        "canonical_sha256": document["canonical_sha256"],
        "issued_at": now,
        "expires_at": now + REVIEW_TTL_SECONDS,
        "development_only": True,
        "independent_validation": False,
    }
    token = _sign(payload, secret)
    return {
        "packet_id": token,
        "packet_version": PACKET_VERSION,
        "claim_type": claim_type,
        "claim_text": payload["claim_text"],
        "evidence": {
            "page_number": payload["page_number"],
            "excerpt": payload["excerpt"],
            "excerpt_sha256": payload["excerpt_sha256"],
            "literal_check": "VERIFIED_PAGE_TEXT_SUBSTRING",
        },
        "context": payload["context"],
        "context_sha256": payload["context_sha256"],
        "checklist": [
            {"key": key, "label": CHECKLIST_LABELS[key]}
            for key in CHECKLIST_KEYS
        ],
        "allowed_reviewers": list(reviewers_from_env()),
        "expires_at": payload["expires_at"],
        "development_only": True,
        "independent_validation": False,
        "status": "AWAITING_EXPLICIT_HUMAN_DECISION",
    }


def verify_packet(token: str, secret: str) -> dict:
    return _verify(token, secret)


def validate_review(
    payload: dict,
    *,
    reviewer_id: str,
    verdict: str,
    checklist: dict,
    rationale: str,
    allowlist: tuple[str, ...],
    checklist_notes: dict | None = None,
) -> dict:
    if not isinstance(reviewer_id, str) or reviewer_id.strip() not in allowlist:
        raise ValueError("REVIEWER_NOT_ALLOWLISTED")
    if verdict not in VERDICTS:
        raise ValueError("REVIEW_VERDICT_INVALID")
    if not isinstance(checklist, dict) or set(checklist) != set(CHECKLIST_KEYS):
        raise ValueError("REVIEW_CHECKLIST_INVALID")
    if not all(isinstance(value, bool) for value in checklist.values()):
        raise ValueError("REVIEW_CHECKLIST_INVALID")
    if verdict == "ADMIT" and not all(checklist.values()):
        raise ValueError("REVIEW_CHECKLIST_NOT_MET")
    if not isinstance(rationale, str) or not (8 <= len(rationale.strip()) <= MAX_RATIONALE_CHARS):
        raise ValueError("REVIEW_RATIONALE_INVALID")
    notes: dict[str, str] = {}
    if checklist_notes is not None:
        if (not isinstance(checklist_notes, dict)
                or not set(checklist_notes) <= set(CHECKLIST_KEYS)):
            raise ValueError("REVIEW_CHECKLIST_NOTES_INVALID")
        for key, note in checklist_notes.items():
            if not isinstance(note, str) or not (1 <= len(note.strip()) <= 500):
                raise ValueError("REVIEW_CHECKLIST_NOTES_INVALID")
            notes[key] = note.strip()
    return {
        "review_version": REVIEW_VERSION,
        "reviewer_id": reviewer_id.strip(),
        "verdict": verdict,
        "checklist": {key: checklist[key] for key in CHECKLIST_KEYS},
        "checklist_notes": notes,
        "rationale": rationale.strip(),
        "development_only": True,
        "independent_validation": False,
    }


def record_review(
    payload: dict,
    review: dict,
    *,
    storage_dir: Path,
    recorded_at: datetime | None = None,
) -> dict:
    storage_dir.mkdir(parents=True, exist_ok=True)
    stamp = (recorded_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    record = {
        **review,
        "packet_version": payload.get("packet_version"),
        "claim_type": payload.get("claim_type"),
        "claim_text": payload.get("claim_text"),
        "page_number": payload.get("page_number"),
        "excerpt_sha256": payload.get("excerpt_sha256"),
        "excerpt": payload.get("excerpt"),
        "context": payload.get("context"),
        "context_sha256": payload.get("context_sha256"),
        "document_id": payload.get("document_id"),
        "source_sha256": payload.get("source_sha256"),
        "canonical_sha256": payload.get("canonical_sha256"),
        "question": payload.get("question"),
        "recorded_at": stamp.isoformat(),
    }
    review_id = sha256(
        json.dumps(record, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:32]
    record["review_id"] = review_id
    target = storage_dir / f"{review_id}.json"
    if target.exists():
        raise ValueError("REVIEW_ALREADY_RECORDED")
    target.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    os.chmod(target, 0o600)
    return record


def decide_development_publication(
    payload: dict,
    review: dict,
    *,
    allowlist: tuple[str, ...],
) -> dict:
    """Development-only gate. Never admits without an explicit ADMIT review."""
    failures = []
    if review.get("reviewer_id") not in allowlist:
        failures.append("REVIEWER_NOT_ALLOWLISTED")
    if review.get("verdict") == "REJECT":
        failures.append("SEMANTIC_REVIEW_REJECTED")
    elif review.get("verdict") == "UNCERTAIN":
        failures.append("SEMANTIC_REVIEW_UNCERTAIN")
    elif review.get("verdict") != "ADMIT":
        failures.append("SEMANTIC_REVIEW_MISSING")
    if review.get("claim_text") != payload.get("claim_text"):
        failures.append("REVIEW_CLAIM_MISMATCH")
    if review.get("excerpt_sha256") != payload.get("excerpt_sha256"):
        failures.append("REVIEW_EVIDENCE_MISMATCH")
    checklist = review.get("checklist") or {}
    if not all(checklist.get(key) is True for key in CHECKLIST_KEYS):
        failures.append("REVIEW_CHECKLIST_NOT_MET")
    if failures:
        return {
            "may_publish": False,
            "reason": failures[0],
            "failures": failures,
            "development_only": True,
            "independent_validation": False,
        }
    return {
        "may_publish": True,
        "reason": None,
        "development_only": True,
        "independent_validation": False,
        "review_id": review.get("review_id"),
        "reviewer_id": review.get("reviewer_id"),
    }
