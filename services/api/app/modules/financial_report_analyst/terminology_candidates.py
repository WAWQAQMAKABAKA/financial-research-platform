"""M126: audited lexical cue-to-source label expansion, retrieval preview ONLY.

No accounting equivalence, no financial-semantic approval, no XBRL element
attribution, no Tushare data, no external requests or protected evaluation GT.
All entries are candidate terminology from the independently checked M126 audit.
Changing this registry requires requalifying retrieval and its versioned identity.
"""
from __future__ import annotations

from functools import lru_cache
from hashlib import sha256
from pathlib import Path
import json
import re
import unicodedata

VERSION = "frp-m126-retrieval-candidates-v1"
REGISTRY_SHA256 = "358ca1368656f0fbc9361957e3fcfbf89ee90e9b54dc006e14d57019c1c8512d"
MAX_MATCHED_CONCEPTS = 8


def _norm(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value)).casefold()


@lru_cache(maxsize=1)
def _records() -> tuple[dict, ...]:
    source = Path(__file__).with_name("terminology_registry_v1.json")
    body = source.read_bytes()
    if sha256(body).hexdigest() != REGISTRY_SHA256:
        raise ValueError("TERMINOLOGY_REGISTRY_SHA_INVALID")
    manifest = json.loads(body)
    if (manifest.get("version") != VERSION
            or manifest.get("status") != "CANDIDATE_ONLY"
            or manifest.get("scope") != "RETRIEVAL_ONLY_NOT_ACCOUNTING_EQUIVALENCE"):
        raise ValueError("TERMINOLOGY_REGISTRY_CONTRACT_INVALID")
    entries = manifest.get("records")
    if not isinstance(entries, list) or len(entries) != 25:
        raise ValueError("TERMINOLOGY_REGISTRY_COUNT_INVALID")
    ids = set()
    for row in entries:
        if (not isinstance(row, dict) or not isinstance(row.get("id"), str)
                or not re.fullmatch(r"[a-z][a-z_]+", row["id"])
                or row["id"] in ids
                or not isinstance(row.get("preferred_zh"), str)
                or not row["preferred_zh"].strip()
                or not isinstance(row.get("kind"), str)
                or not isinstance(row.get("origin"), str)
                or not isinstance(row.get("retrieval_cues"), list)
                or any(not isinstance(x, str) or len(_norm(x)) < 2
                       for x in row["retrieval_cues"])
                or not isinstance(row.get("not_equivalent_to"), list)):
            raise ValueError("TERMINOLOGY_REGISTRY_RECORD_INVALID")
        ids.add(row["id"])
    by_id = {x["id"]: x for x in entries}
    for row in entries:
        for distinct_id in row["not_equivalent_to"]:
            if (distinct_id not in by_id
                    or row["id"] not in by_id[distinct_id]["not_equivalent_to"]):
                raise ValueError("TERMINOLOGY_NON_EQUIVALENCE_INVALID")
    return tuple(entries)


def candidate_probe(question: str) -> dict:
    """Propose separate concept labels from literal cue hits; never merge them."""
    if not isinstance(question, str) or len(question) > 240:
        raise ValueError("TERMINOLOGY_QUESTION_INVALID")
    raw = _norm(question)
    candidates = []
    matched_cues = []
    for row in _records():
        # If the customer already uses the exact label, keep the M122 ranking.
        # A shorter cue contained inside a preferred label must not trigger.
        if _norm(row["preferred_zh"]) in raw:
            continue
        matched = [x for x in row["retrieval_cues"] if _norm(x) in raw]
        if not matched:
            continue
        if len(candidates) >= MAX_MATCHED_CONCEPTS:
            # Do not silently truncate an ambiguous registry match.
            raise ValueError("TERMINOLOGY_AMBIGUOUS_TOO_MANY_CANDIDATES")
        matched_cues.extend(matched)
        candidates.append({
            "concept_id": row["id"],
            "preferred_zh": row["preferred_zh"],
            "kind": row["kind"],
            "origin": row["origin"],
            "not_equivalent_to": row["not_equivalent_to"],
        })
    candidate_ids = {x["concept_id"] for x in candidates}
    has_distinct = any(
        set(x["not_equivalent_to"]) & candidate_ids for x in candidates
    )
    return {
        "version": VERSION,
        "registry_sha256": REGISTRY_SHA256,
        "status": "ACTIVATED" if candidates else "NO_TRIGGER",
        "matched_cues": list(dict.fromkeys(matched_cues)),
        "candidates": candidates,
        "distinct_concepts_warning": (
            "NON_EQUIVALENT_CANDIDATES" if has_distinct else "NOT_ASSESSED"
        ),
        "review": "RETRIEVAL_CUES_ONLY_NOT_FINANCIAL_EQUIVALENCE",
    }


def candidate_score(excerpt: str, probe: dict) -> float:
    """Bounded exact preferred-label boost; one candidate does not equal a fact."""
    if probe["status"] != "ACTIVATED":
        return 0.0
    haystack = _norm(excerpt)
    # Prefer actual filing vocabulary; bounded sum avoids free expansion text.
    return sum(4.0 for item in probe["candidates"]
               if _norm(item["preferred_zh"]) in haystack)
