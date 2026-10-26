"""M123: provenance-preserving statement-heading cues for retrieval candidates.

Cues are literal standalone canonical lines, not table attribution or financial
semantic judgments. No issuer-specific pages, amounts, questions, or model calls.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.evidence.pdf_canonicalizer import CanonicalDocument

CONTEXT_VERSION = "frp-standalone-statement-heading-cue-v1"
STATEMENT_HEADINGS = frozenset({
    "合并资产负债表", "母公司资产负债表",
    "合并利润表", "母公司利润表",
    "合并现金流量表", "母公司现金流量表",
    "合并所有者权益变动表", "母公司所有者权益变动表",
})


@dataclass(frozen=True)
class _Heading:
    page: int
    start: int
    end: int
    value: str


def _standalone_headings(document: CanonicalDocument) -> tuple[_Heading, ...]:
    """Read exact complete lines only; prose mentions are never scope cues."""
    found: list[_Heading] = []
    text = document.canonical_text
    for page in document.pages:
        cursor = page.content_start
        body = text[page.content_start:page.content_end]
        for line in body.splitlines(keepends=True):
            candidate = line.strip(" \t\r\n\u3000")
            if candidate in STATEMENT_HEADINGS:
                prefix_len = len(line) - len(line.lstrip(" \t\u3000"))
                start = cursor + prefix_len
                end = start + len(candidate)
                if text[start:end] != candidate:
                    raise ValueError("HEADING_CANONICAL_SPAN_INVALID")
                found.append(_Heading(page.page_number, start, end, candidate))
            cursor += len(line)
    return tuple(found)


def attach_heading_context(
    document: CanonicalDocument, evidence: list[dict],
) -> tuple[list[dict], str]:
    """Annotate evidence, never promote headings into verified metric scopes.

    The most recent standalone financial-statement heading is only surfaced
    when it precedes the chunk and is on the same or immediately prior page.
    An intervening heading INSIDE the chunk makes scope unresolved.
    """
    headings = _standalone_headings(document)
    augmented = []
    seen: set[str] = set()
    for item in evidence:
        page = item["source_page"]
        start, end = item["canonical_start"], item["canonical_end"]
        if (
            not isinstance(page, int) or isinstance(page, bool)
            or not isinstance(start, int) or isinstance(start, bool)
            or not isinstance(end, int) or isinstance(end, bool)
            or page < 1 or page > len(document.pages)
            or not (document.pages[page - 1].content_start <= start < end <=
                    document.pages[page - 1].content_end)
            or document.canonical_text[start:end] != item["source_excerpt"]
        ):
            raise ValueError("HEADING_CUE_EVIDENCE_SPAN_INVALID")
        previous = next((h for h in reversed(headings) if h.end <= start), None)
        crosses_heading = any(h.start < end and h.end > start for h in headings)
        if (previous is None or page - previous.page > 1 or crosses_heading):
            cue = {
                "status": "UNRESOLVED",
                "heading_verbatim": None,
                "heading_page": None,
                "heading_start": None,
                "heading_end": None,
            }
        else:
            seen.add(previous.value)
            cue = {
                "status": "STANDALONE_HEADING_CANDIDATE",
                "heading_verbatim": previous.value,
                "heading_page": previous.page,
                "heading_start": previous.start,
                "heading_end": previous.end,
            }
        augmented.append({**item, "statement_heading_cue": cue})

    # Multiple headings indicate a real context hazard. Absence of a warning
    # MUST NOT be interpreted as successful accounting-scope review.
    alert = (
        "MULTIPLE_STATEMENT_HEADING_CANDIDATES"
        if len(seen) > 1 else "NOT_ASSESSED"
    )
    return augmented, alert
