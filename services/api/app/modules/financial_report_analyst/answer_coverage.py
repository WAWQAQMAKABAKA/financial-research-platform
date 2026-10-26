"""M125: honest, deterministic question-phrase visibility audit.

This is *not* a relevance, evidence-sufficiency, or financial-semantic review.
No issuer, report, question, or evaluation-answer tables; no LLM/network calls.
An exact normalized question phrase may miss valid paraphrases and may
match irrelevant text. A visible match does not establish a correct answer.
"""
from __future__ import annotations

from hashlib import sha256
import re
import unicodedata

VERSION = "frp-question-phrase-visibility-v1"
BASIS = "EXACT_NORMALIZED_QUESTION_PHRASES_ONLY"
REVIEW = "COVERAGE_NOT_SEMANTICALLY_QUALIFIED"
_MAX_FACETS = 4
# These are general linguistic separators, not issuer or question-category routes.
_SPLIT = re.compile(r"(?:以及|并且|和|与|及|、|，|,|；|;|\band\b)", re.IGNORECASE)
_QUESTION_TAIL = re.compile(
    r"(?:有哪些披露|有何披露|有哪些|表现如何|情况如何|如何|是什么|怎么样|什么情况)[？?。\s]*$",
    re.IGNORECASE,
)


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value)).casefold()


def _facets(question: str) -> tuple[list[str], str]:
    trimmed = _QUESTION_TAIL.sub("", question.strip()).rstrip("？?。. ")
    if not trimmed:
        trimmed = question.strip()
    chunks = [part.strip(" ?？。") for part in _SPLIT.split(trimmed)]
    distinct = list(dict.fromkeys(part for part in chunks if len(_normalize(part)) >= 2))
    # Do not imply complete decomposition if an arbitrary question is long,
    # ambiguous, or split into more than the supported display bound.
    if not (1 <= len(distinct) <= _MAX_FACETS):
        return [trimmed[:240]], "FALLBACK_SINGLE_QUESTION_PHRASE"
    return distinct, "SURFACE_CONJUNCTION_SPLIT"


def build_coverage_probe(*, question: str, retrieval_id: str,
                         draft_id: str, evidence: list[dict],
                         claims: list[dict]) -> dict:
    """Compute only literal visibility of question phrases in source and draft.

    Requires upstream original-PDF/PIT verification and claim-to-quote review.
    Enforce reference integrity even for this non-authoritative diagnostic.
    """
    if (not isinstance(question, str) or not question.strip()
            or len(question) > 240 or len(question.encode("utf-8")) > 800
            or any(not isinstance(x, str) or not re.fullmatch(r"[a-f0-9]{64}", x)
                   for x in (retrieval_id, draft_id))
            or not isinstance(evidence, list) or not (2 <= len(evidence) <= 5)
            or not isinstance(claims, list) or not (1 <= len(claims) <= 3)):
        raise ValueError("COVERAGE_INPUT_INVALID")
    by_id = {}
    for hit in evidence:
        if (not isinstance(hit, dict)
                or not isinstance(hit.get("evidence_id"), str)
                or not re.fullmatch(r"[a-f0-9]{64}", hit["evidence_id"])
                or hit["evidence_id"] in by_id
                or not isinstance(hit.get("source_excerpt"), str)
                or not hit["source_excerpt"].strip()):
            raise ValueError("COVERAGE_EVIDENCE_INVALID")
        by_id[hit["evidence_id"]] = hit
    observed_claims = set()
    for claim in claims:
        if (not isinstance(claim, dict)
                or claim.get("claim_id") != f"C{len(observed_claims)+1}"
                or claim.get("evidence_id") not in by_id
                or not isinstance(claim.get("text"), str)
                or not isinstance(claim.get("source_quote"), str)
                or _normalize(claim["source_quote"]) not in
                    _normalize(by_id[claim["evidence_id"]]["source_excerpt"])
                or not isinstance(claim.get("review"), dict)
                or claim["review"].get("verdict") != "UNCERTAIN"):
            raise ValueError("COVERAGE_CLAIM_BINDING_INVALID")
        observed_claims.add(claim["claim_id"])
    facets, splitting = _facets(question)
    items = []
    for facet in facets:
        phrase = _normalize(facet)
        source_ids = [hit["evidence_id"] for hit in evidence
                      if phrase in _normalize(hit["source_excerpt"])]
        claim_ids = [claim["claim_id"] for claim in claims
                     if phrase in _normalize(claim["text"])
                     and phrase in _normalize(claim["source_quote"])]
        # Never report 'answered', 'complete', 'missing fact', or 'reviewed'.
        literal_status = (
            "PHRASE_VISIBLE_IN_SOURCE_AND_DRAFT" if claim_ids
            else "PHRASE_VISIBLE_IN_SOURCE_ONLY" if source_ids
            else "PHRASE_NOT_LOCATED_LEXICALLY"
        )
        items.append({
            "question_phrase": facet,
            "literal_status": literal_status,
            "source_evidence_ids": source_ids,
            "draft_claim_ids": claim_ids,
        })
    review_id = sha256("|".join((VERSION, retrieval_id, draft_id, question)).encode()).hexdigest()
    return {
        "coverage_id": review_id,
        "coverage_version": VERSION,
        "basis": BASIS,
        "segmentation": splitting,
        "review": REVIEW,
        "facets": items,
        "limitations": (
            "Surface phrase overlap only. Synonyms, paraphrases, causal and financial "
            "semantics, missing evidence, and substantive answer completeness are "
            "NOT evaluated. A match is not proof; absence is not proof of omission."
        ),
    }
