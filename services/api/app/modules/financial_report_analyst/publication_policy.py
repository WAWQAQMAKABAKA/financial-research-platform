"""M1 facts-only publication policy.

The only place in the platform that may decide a claim is fit for a customer.
It publishes nothing itself: it inspects an already built source draft and
approves publication only when every published claim is an OBSERVED_FACT with
manifest-bound identity, span linkage, period/unit agreement and a literal
ADMIT review.

Comparative, inferential, forward-looking or unreviewed claims are never
publishable here. They are reported as withheld, never upgraded. Adding a
label or a status constant cannot approve anything: every condition below is
re-verified from the draft on every call.
"""
from __future__ import annotations

from datetime import datetime
import re
import unicodedata

from app.evidence.corpus_manifest import CorpusDocument

POLICY_VERSION = "m1-facts-only-publication-v1"

FACTS_ONLY = "FACTS_ONLY"
BLOCKED = "BLOCKED"
PUBLICATION_LABEL = "仅展示已核对的披露事实 · 不含财务趋势判断"

ALLOWED_REVIEWER = "native-pdf-cell-literal-reviewer-v1"
ALLOWED_RATIONALE = "LITERAL_CELL_AND_HEADING_SOURCE_CHECK_ONLY"
LITERAL_REVIEW_SCOPE = "LITERAL_CELL_LOCATION_ONLY"
SPAN_STATUS = "NOT_PROVEN_FROM_TABLE_GEOMETRY"
OBSERVED_FACT = "OBSERVED_FACT"

_AMOUNT = re.compile(r"-?(?:0|[1-9]\d{0,2}(?:,\d{3})+|[1-9]\d*)\.\d{2}\Z")
_EVIDENCE_ID = re.compile(r"^[0-9a-f]{64}$")

# Capabilities that exist in the platform but cannot be published in M1.
WITHHELD_CAPABILITIES = (
    ("PERIOD_COMPARISON", "跨期或同比比较需要独立的财务语义审查，本报告不发布。"),
    ("CROSS_ENTITY_COMPARISON", "跨发行人比较需要独立的财务语义审查，本报告不发布。"),
    ("ANALYST_INFERENCE", "推断与归因需要可核验的假设和独立审查，本报告不发布。"),
    ("FORWARD_VIEW", "前瞻性判断不属于披露事实，本报告不发布。"),
    ("MANAGEMENT_EXPLANATION", "管理层叙述尚未完成独立语义核验，本报告不发布。"),
)


def _norm(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value))


def period_expectations(report_period: str) -> tuple[str, str] | None:
    """Map a report period to its verbatim column and printed date range."""
    year, half = report_period[:4], report_period[4:]
    if not year.isdigit():
        return None
    if half == "H1":
        return f"{year} 年半年度", rf"{year}年1[—－-]6月"
    if half == "FY":
        return f"{year} 年度", rf"{year}年1[—－-]12月"
    return None


def _withheld(reason: str, claim_id: str | None = None) -> dict:
    return {
        "policy_version": POLICY_VERSION,
        "status": "PUBLICATION_WITHHELD",
        "may_publish": False,
        "research_publication": BLOCKED,
        "publication_label": PUBLICATION_LABEL,
        "financial_semantic_review": "NOT_PERFORMED",
        "published_claim_ids": [],
        "withheld": [] if claim_id is None else [{
            "claim_id": claim_id, "kind": None,
            "status": "NOT_PUBLISHED", "reason": reason,
        }],
        "withheld_capabilities": _capabilities(),
        "reason": reason,
    }


def _capabilities() -> list[dict]:
    return [
        {"kind": kind, "status": "NOT_PUBLISHED", "reason": text}
        for kind, text in WITHHELD_CAPABILITIES
    ]


def decide_publication(
    draft: dict,
    document: CorpusDocument,
    *,
    expected_statement_kind: str,
    expected_row_label: str | None = None,
    expected_row_labels: tuple[str, ...] | None = None,
    as_of: datetime,
    verify_evidence=None,
) -> dict:
    """Approve facts-only publication, or withhold the whole report.

    ``verify_evidence(evidence_id) -> bool`` may be supplied by the caller to
    re-check the canonical span against the source text. Without it, the policy
    still requires the literal reviewer's ADMIT and the span status flags.

    ``expected_row_labels`` allows a retrieval-derived selection to publish more
    than one literal row. Each published claim must still match one of the
    supplied labels exactly (whitespace-normalized); the policy never accepts a
    label the caller did not ask for.
    """
    expected_labels = (
        tuple(expected_row_labels) if expected_row_labels is not None
        else (() if expected_row_label is None else (expected_row_label,))
    )
    if not expected_labels:
        return _withheld("EXPECTED_SELECTION_MISSING")

    if not isinstance(draft, dict) or draft.get("status") != "SOURCE_DRAFT_READY":
        return _withheld("SOURCE_DRAFT_NOT_READY")

    observations = draft.get("observations")
    claims = draft.get("claims")
    reviews = draft.get("reviews")
    if not all(isinstance(items, list) for items in (observations, claims, reviews)):
        return _withheld("CLAIM_GRAPH_INCOMPLETE")
    if not observations or not claims:
        return _withheld("CLAIM_GRAPH_INCOMPLETE")
    if len(observations) != len(claims):
        return _withheld("CLAIM_GRAPH_LENGTH_MISMATCH")

    # PIT is checked against the manifest document, never the draft's own claim.
    try:
        document.to_source_document().require_available(as_of)
    except ValueError:
        return _withheld("PIT_UNAVAILABLE")

    # Draft-level identity must already be the manifest identity.
    for key in ("document_id", "source_sha256", "canonical_sha256", "source_url"):
        if draft.get(key) != getattr(document, key):
            return _withheld("SOURCE_IDENTITY_MISMATCH")

    expected = period_expectations(document.report_period)
    if expected is None:
        return _withheld("UNSUPPORTED_REPORT_PERIOD")
    expected_column, printed_period = expected

    review_by_claim = {}
    for review in reviews:
        if not isinstance(review, dict):
            return _withheld("REVIEW_SHAPE_INVALID")
        claim_id = review.get("claim_id")
        if not isinstance(claim_id, str) or claim_id in review_by_claim:
            return _withheld("REVIEW_ID_INVALID")
        review_by_claim[claim_id] = review

    published, withheld, seen_evidence = [], [], set()

    for observation, claim in zip(observations, claims):
        if not isinstance(observation, dict) or not isinstance(claim, dict):
            return _withheld("CLAIM_GRAPH_SHAPE_INVALID")

        claim_id = claim.get("claim_id")
        kind = claim.get("kind")
        if not isinstance(claim_id, str) or not claim_id:
            return _withheld("CLAIM_ID_INVALID")

        if kind != OBSERVED_FACT:
            withheld.append({
                "claim_id": claim_id, "kind": kind,
                "status": "NOT_PUBLISHED", "reason": "NON_FACT_CLAIM_NOT_PUBLISHABLE",
            })
            continue

        evidence_ids = claim.get("evidence_ids")
        if (not isinstance(evidence_ids, list) or len(evidence_ids) != 1
                or not isinstance(evidence_ids[0], str)
                or not _EVIDENCE_ID.fullmatch(evidence_ids[0])):
            return _withheld("FACT_EVIDENCE_ID_INVALID", claim_id)
        evidence_id = evidence_ids[0]
        if evidence_id in seen_evidence:
            return _withheld("DUPLICATE_EVIDENCE_ID", claim_id)
        seen_evidence.add(evidence_id)

        if (observation.get("claim_id") != claim_id
                or observation.get("evidence_id") != evidence_id):
            return _withheld("CLAIM_EVIDENCE_LINK_MISMATCH", claim_id)

        # Source identity must come from the manifest document, not the draft.
        # Per-observation identity fields are optional (the workspace carries
        # them at the draft level) but must agree when present.
        for key in ("document_id", "source_sha256", "canonical_sha256", "source_url"):
            if key in observation and observation[key] != getattr(document, key):
                return _withheld("SOURCE_IDENTITY_MISMATCH", claim_id)

        # Category linkage: the row/statement actually selected for this report.
        if (
            observation.get("statement_type_candidate") != expected_statement_kind
            or _norm(observation.get("row_label"))
                not in {_norm(label) for label in expected_labels}
            or _norm(observation.get("column_header")) != _norm(expected_column)
        ):
            return _withheld("SELECTION_MISMATCH", claim_id)

        # Period linkage: printed reporting period and unit must agree.
        context = _norm(observation.get("statement_context"))
        if re.search(printed_period, context) is None:
            return _withheld("PERIOD_LINKAGE_MISMATCH", claim_id)
        if "单位:元" not in context or "币种:人民币" not in context:
            return _withheld("UNIT_CONTEXT_MISMATCH", claim_id)

        if not _AMOUNT.fullmatch(str(observation.get("value_verbatim", "")).strip()):
            return _withheld("VALUE_FORMAT_INVALID", claim_id)

        page_number = observation.get("page_number")
        if (not isinstance(page_number, int) or isinstance(page_number, bool)
                or page_number < 1):
            return _withheld("PAGE_INVALID", claim_id)

        if (observation.get("source_text_span_status") != SPAN_STATUS
                or observation.get("review_scope") != LITERAL_REVIEW_SCOPE):
            return _withheld("SPAN_SCOPE_MISMATCH", claim_id)

        review = review_by_claim.get(claim_id)
        if review is None:
            return _withheld("REVIEW_MISSING", claim_id)
        if review.get("verdict") != "ADMIT":
            return _withheld("REVIEW_NOT_ADMIT", claim_id)
        if review.get("reviewer_id") != ALLOWED_REVIEWER:
            return _withheld("REVIEWER_NOT_ALLOWLISTED", claim_id)
        if review.get("rationale") != ALLOWED_RATIONALE:
            return _withheld("REVIEW_RATIONALE_NOT_LITERAL_SCOPE", claim_id)

        if verify_evidence is not None and not verify_evidence(evidence_id):
            return _withheld("EVIDENCE_SPAN_NOT_VERIFIED", claim_id)

        published.append(claim_id)

    if not published:
        result = _withheld("NO_PUBLISHABLE_FACT")
        result["withheld"] = withheld
        return result

    return {
        "policy_version": POLICY_VERSION,
        "status": "PUBLICATION_APPROVED",
        "may_publish": True,
        "research_publication": FACTS_ONLY,
        "publication_label": PUBLICATION_LABEL,
        "financial_semantic_review": "NOT_PERFORMED",
        "published_claim_ids": published,
        "withheld": withheld,
        "withheld_capabilities": _capabilities(),
        "reason": None,
    }
