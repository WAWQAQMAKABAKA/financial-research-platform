"""M4: deterministic multi-requirement evidence planning.

A question that asks for two or three independent disclosure facts is split into
requirements. Each requirement is resolved against the verified table index; the
planner reports what is satisfied and what is missing, and never turns a missing
requirement into an inferred or comparative answer.

This module proposes requirements and coverage only. It does not approve
publication: the caller re-locates every row, runs the literal reviewer and the
facts-only policy.
"""
from __future__ import annotations

import re
import unicodedata

from app.modules.financial_report_analyst import question_selection as qs

VERSION = "m4-evidence-requirements-v1"
MAX_REQUIREMENTS = 6

# "及" alone is deliberately absent: it occurs inside row labels such as
# 税金及附加 and would split a single metric into two. "以及" still splits.
_SPLIT = re.compile(
    r"(?:以及|并且|和|与|、|，|,|；|;|\band\b)", re.IGNORECASE
)
_TAIL = re.compile(
    r"(?:分别是多少|分别多少|各是多少|分别是|分别|是多少|有哪些|如何|怎么样|什么情况)"
    r"[？?。\s]*$"
)


def _norm(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value))


def split_facets(question: str) -> list[str]:
    """Split on conjunctions only; otherwise the question is one facet."""
    if not isinstance(question, str):
        return []
    trimmed = _TAIL.sub("", question.strip()).rstrip("？?。. ")
    parts = [part.strip(" ?？。") for part in _SPLIT.split(trimmed)]
    distinct = [part for part in dict.fromkeys(parts) if len(_norm(part)) >= 2]
    if len(distinct) < 2:
        return [question.strip()]
    return distinct


def plan_requirements(
    index: dict,
    *,
    question: str,
    report_period: str,
    column_header: str,
    retrieval_hits: list[dict] | None = None,
    pinned_rows: dict[str, str] | None = None,
    proposed_facets: list[str] | None = None,
) -> dict | None:
    """Return a plan, a scope-ambiguity signal, or None for single-fact questions."""
    facets = split_facets(question)
    facets_source = "DETERMINISTIC_SPLIT"
    if proposed_facets and len(proposed_facets) >= 2:
        facets = list(proposed_facets)
        facets_source = "LLM_PROPOSAL_VALIDATED"
    if len(facets) < 2:
        return None
    if len(facets) > MAX_REQUIREMENTS:
        return {
            "status": "TOO_MANY_REQUIREMENTS",
            "reason": "TOO_MANY_REQUIREMENTS",
            "detected": len(facets),
            "max": MAX_REQUIREMENTS,
            "facets": facets,
            "facets_source": facets_source,
            "present": [],
            "requirements": [],
        }

    section_pages = qs._section_pages(index)
    present = [kind for kind in qs.INCOME_STATEMENT_KINDS if kind in section_pages]
    if not present:
        return {"status": "WITHHELD", "reason": "NO_STATEMENT_SCOPE",
                "present": [], "requirements": [], "facets": facets}

    question_norm = qs._norm(question)
    matches_by_kind = {
        kind: qs._row_matches(index, kind, question_norm) for kind in present
    }
    kind, basis, reason = qs._resolve_statement_scope(
        question_norm=question_norm,
        present=present,
        section_pages=section_pages,
        retrieval_hits=list(retrieval_hits or []),
        matches_by_kind=matches_by_kind,
    )
    if kind is None:
        return {
            "status": "SCOPE_AMBIGUOUS" if reason == "AMBIGUOUS_STATEMENT_SCOPE"
            else "WITHHELD",
            "reason": reason or "NO_STATEMENT_SCOPE",
            "present": present,
            "requirements": [],
            "facets": facets,
        }

    requirements = []
    for number, facet in enumerate(facets, start=1):
        pinned = (pinned_rows or {}).get(facet)
        if pinned:
            requirements.append({
                "requirement_id": f"R{number}", "facet": facet,
                "status": "SATISFIED",
                "row": {"row_label": pinned, "core": qs.row_label_core(pinned),
                        "match_chars": len(qs.row_label_core(pinned))},
            })
            continue
        selection = qs.select_cells(
            index, question=facet, report_period=report_period,
            column_header=column_header, retrieval_hits=[],
            forced_statement_kind=kind,
        )
        requirement_id = f"R{number}"
        if selection["status"] == "SELECTION_READY" and len(selection["rows"]) == 1:
            requirements.append({
                "requirement_id": requirement_id, "facet": facet,
                "status": "SATISFIED", "row": selection["rows"][0],
            })
        elif selection["status"] == "SELECTION_READY":
            requirements.append({
                "requirement_id": requirement_id, "facet": facet,
                "status": "AMBIGUOUS",
                "rows": [row["row_label"] for row in selection["rows"]],
            })
        else:
            requirements.append({
                "requirement_id": requirement_id, "facet": facet,
                "status": selection.get("reason") or "UNRESOLVED",
            })

    return {
        "status": "PLAN_READY",
        "statement_kind": kind,
        "selection_basis": basis,
        "facets": facets,
        "facets_source": facets_source,
        "present": present,
        "requirements": requirements,
    }
