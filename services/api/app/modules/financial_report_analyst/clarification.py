"""M3: metric-identity clarification for the 600760 facts-only report.

A question whose metric phrase does not literally match a source row is not
simply rejected: when exactly two to four verified rows could be what the user
meant, the platform asks the user to choose. The options come from the verified
table index (or from a validated LLM proposal), never from free text.

This module generates options and a signed, expiring clarification token. It
never approves publication and never changes the facts-only gate: the chosen
option is passed back through retrieval, literal review and the policy as a
forced selection.
"""
from __future__ import annotations

import base64
from collections import Counter
import hashlib
import hmac
import json
import re
import time
import unicodedata

from pydantic import Field

from app.evidence.contracts import StrictRecord
from app.evidence.corpus_manifest import CorpusDocument
from app.evidence.document_index import SECTION_TITLES
from app.modules.financial_report_analyst import question_selection as qs

CLARIFICATION_TTL_SECONDS = 600
TOKEN_VERSION = 1

# Common issuer/filing bigrams that must not count as metric evidence.
_STOP_BIGRAMS = frozenset({
    "公司", "股份", "有限", "责任", "年度", "半年", "上半", "报告",
    "证券", "代码", "财务", "报表", "利润表", "现金", "流量",
})
_CJK = re.compile(r"[\u3400-\u9fff]")


def _norm(value: object) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value)) if isinstance(value, str) else ""


def option_id(document: CorpusDocument, statement_kind: str, row_label: str) -> str:
    return hashlib.sha256(
        f"{document.document_id}|{document.canonical_sha256}|"
        f"{statement_kind}|{_norm(row_label)}".encode("utf-8")
    ).hexdigest()


def scope_option_id(document: CorpusDocument, statement_kind: str) -> str:
    return hashlib.sha256(
        f"{document.document_id}|{document.canonical_sha256}|STATEMENT_SCOPE|"
        f"{statement_kind}".encode("utf-8")
    ).hexdigest()


def _bigrams(text: str) -> set[str]:
    compact = _norm(text)
    return {
        compact[i:i + 2] for i in range(len(compact) - 1)
        if _CJK.match(compact[i]) and _CJK.match(compact[i + 1])
    }


def closed_options(index: dict, document: CorpusDocument, statement_kind: str) -> list[dict]:
    """Every row of one verified statement, as a server-selected candidate."""
    return [
        {
            "option_id": option_id(document, statement_kind, label),
            "row_label": label,
            "core": qs.row_label_core(label),
            "statement_kind": statement_kind,
            "statement_title": SECTION_TITLES[statement_kind],
        }
        for label in qs._row_labels(index, statement_kind)
    ]


def near_match_options(closed: list[dict], question: str) -> list[dict]:
    """Deterministic fallback: rows sharing a *rare* CJK bigram.

    A generic bigram such as 利润 is shared by many rows and would not
    disambiguate; only bigrams that occur in few rows count. This is a lexical
    heuristic, not a metric-identity decision.
    """
    question_grams = _bigrams(question)
    if not closed:
        return []
    doc_freq = Counter()
    for option in closed:
        doc_freq.update(set(_bigrams(option["core"])))
    rare = {gram for gram, count in doc_freq.items() if count <= 4}

    scored = []
    for option in closed:
        shared = (question_grams & _bigrams(option["core"]) & rare) - _STOP_BIGRAMS
        if shared:
            scored.append((len(shared), option))
    scored.sort(key=lambda item: (-item[0], item[1]["row_label"]))
    return [option for _, option in scored]


class ClarificationOption(StrictRecord):
    option_id: str = Field(min_length=1)
    row_label: str = Field(min_length=1)
    core: str = Field(min_length=1)
    statement_kind: str = Field(min_length=1)
    statement_title: str = Field(min_length=1)


def _secret(env_token: str) -> str:
    return hashlib.sha256(env_token.encode("utf-8")).hexdigest()


def sign_clarification(*, question: str, document: CorpusDocument,
                       report_key: str, statement_kind: str | None,
                       option_ids: list[str], secret: str,
                       kind: str = "METRIC_IDENTITY",
                       extra: dict | None = None) -> str:
    payload = {
        "v": TOKEN_VERSION,
        "kind": kind,
        "question_sha256": hashlib.sha256(question.encode("utf-8")).hexdigest(),
        "document_id": document.document_id,
        "canonical_sha256": document.canonical_sha256,
        "report_key": report_key,
        "statement_kind": statement_kind,
        "option_ids": sorted(option_ids),
        "issued_at": int(time.time()),
        **(extra or {}),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    mac = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return f"{encoded}.{mac}"


def verify_clarification(token: str, secret: str) -> dict:
    """Return the payload, or raise on tamper, expiry, or bad shape."""
    if not isinstance(token, str) or "." not in token:
        raise ValueError("CLARIFICATION_TOKEN_INVALID")
    encoded, mac = token.rsplit(".", 1)
    try:
        raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
    except Exception:
        raise ValueError("CLARIFICATION_TOKEN_INVALID") from None
    if not hmac.compare_digest(
        hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest(), mac
    ):
        raise ValueError("CLARIFICATION_TOKEN_INVALID")
    try:
        payload = json.loads(raw)
    except ValueError:
        raise ValueError("CLARIFICATION_TOKEN_INVALID") from None
    if (not isinstance(payload, dict) or payload.get("v") != TOKEN_VERSION
            or not isinstance(payload.get("option_ids"), list)
            or payload.get("kind") not in {"METRIC_IDENTITY", "STATEMENT_SCOPE"}):
        raise ValueError("CLARIFICATION_TOKEN_INVALID")
    issued_at = payload.get("issued_at")
    now = int(time.time())
    if not isinstance(issued_at, int) or now - issued_at > CLARIFICATION_TTL_SECONDS:
        raise ValueError("CLARIFICATION_TOKEN_EXPIRED")
    if issued_at - now > 60:
        raise ValueError("CLARIFICATION_TOKEN_INVALID")
    return payload


def build_clarification(
    *,
    report_key: str,
    document: CorpusDocument,
    index: dict,
    question: str,
    statement_kind: str,
    secret: str,
    proposed_option_ids: list[str] | None = None,
    interpretation_rationale: str | None = None,
    interpretation_status: str | None = None,
    interpretation_reason: str | None = None,
) -> dict | None:
    """Build a clarification or return None when it should not be asked.

    ``proposed_option_ids`` are LLM candidate IDs, validated against the closed
    option set; the deterministic near-match set is the no-LLM fallback.
    """
    closed = closed_options(index, document, statement_kind)
    by_id = {option["option_id"]: option for option in closed}

    candidates: list[dict] = []
    basis = "NEAR_MATCH"
    if proposed_option_ids:
        valid = [by_id[i] for i in proposed_option_ids if i in by_id]
        if 2 <= len(valid) <= 4:
            candidates = valid
            basis = "LLM_PROPOSAL_VALIDATED"

    if not candidates:
        fallback = near_match_options(closed, question)
        if 2 <= len(fallback) <= 4:
            candidates = fallback
            basis = "NEAR_MATCH"

    if not candidates or not (2 <= len(candidates) <= 4):
        return None

    option_ids = [option["option_id"] for option in candidates]
    token = sign_clarification(
        question=question, document=document, report_key=report_key,
        statement_kind=statement_kind, option_ids=option_ids, secret=secret,
    )
    return {
        "status": "CLARIFICATION_REQUIRED",
        "kind": "METRIC_IDENTITY",
        "reason": "METRIC_IDENTITY_AMBIGUOUS",
        "report_key": report_key,
        "document_id": document.document_id,
        "canonical_sha256": document.canonical_sha256,
        "question": question,
        "clarification_id": token,
        "option_basis": basis,
        "options": [
            {
                "option_id": option["option_id"],
                "row_label": option["row_label"],
                "core": option["core"],
                "statement_kind": option["statement_kind"],
                "statement_title": option["statement_title"],
            }
            for option in candidates
        ],
        "interpretation": {
            "status": interpretation_status or (
                "UNVERIFIED_PROPOSAL" if proposed_option_ids is not None
                else "NOT_PERFORMED"
            ),
            "reason": interpretation_reason,
            "rationale": interpretation_rationale,
        },
        "financial_semantic_review": "NOT_PERFORMED",
        "research_publication": "BLOCKED",
    }


def build_scope_clarification(
    *,
    report_key: str,
    document: CorpusDocument,
    present_kinds: list[str],
    question: str,
    secret: str,
) -> dict | None:
    """Ask which statement the question means, when both hold matching rows."""
    kinds = [kind for kind in present_kinds if kind in SECTION_TITLES]
    if not (2 <= len(kinds) <= 3):
        return None
    options = [
        {
            "option_id": scope_option_id(document, kind),
            "statement_kind": kind,
            "statement_title": SECTION_TITLES[kind],
            "core": SECTION_TITLES[kind],
            "row_label": SECTION_TITLES[kind],
        }
        for kind in kinds
    ]
    token = sign_clarification(
        question=question, document=document, report_key=report_key,
        statement_kind=None, option_ids=[option["option_id"] for option in options],
        secret=secret, kind="STATEMENT_SCOPE",
    )
    return {
        "status": "CLARIFICATION_REQUIRED",
        "kind": "STATEMENT_SCOPE",
        "reason": "STATEMENT_SCOPE_AMBIGUOUS",
        "report_key": report_key,
        "document_id": document.document_id,
        "canonical_sha256": document.canonical_sha256,
        "question": question,
        "clarification_id": token,
        "option_basis": "SOURCE_STATEMENTS",
        "options": options,
        "interpretation": {
            "status": "NOT_PERFORMED",
            "reason": None,
            "rationale": None,
        },
        "financial_semantic_review": "NOT_PERFORMED",
        "research_publication": "BLOCKED",
    }
