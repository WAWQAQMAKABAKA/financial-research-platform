"""Bounded, source-located financial table-cell *candidates*.

Consumes an in-memory result from ``index_document``. This module does not
supply accounting interpretations, comparison conclusions, or publication
permission. Trusted callers must regenerate the index from the hash-verified
original PDF; an arbitrary loaded JSON manifest is not an authenticated source.

No issuer-specific figures, pages, table dimensions, or benchmark answers.
"""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from pathlib import Path
import re
import unicodedata

import pymupdf

from app.evidence.contracts import SourceDocument
from app.evidence.document_index import SECTION_TITLES, index_document

_DASHES = frozenset(("—", "–", "-", "―", "－"))


def _norm(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value))


def _blocked(status: str, reason: str) -> dict:
    return {
        "status": status,
        "reason": reason,
        "candidates": [],
        "financial_semantic_review": "NOT_PERFORMED",
        "research_publication": "BLOCKED",
    }


def _index_table(index: dict, section: dict) -> dict:
    """Require exact section -> page/table binding, never search by a guessed page."""
    n, i = section["page_number"], section["table_index"]
    if not (isinstance(n, int) and 1 <= n <= index["page_count"]):
        raise ValueError("INVALID_SECTION_PAGE")
    page = index["pages"][n - 1]
    if page["page_number"] != n:
        raise ValueError("INDEX_PAGE_ORDER_MISMATCH")
    found = [t for t in page["tables"] if t["table_index"] == i]
    if len(found) != 1:
        raise ValueError("SECTION_TABLE_IDENTITY_MISMATCH")
    table = found[0]
    if (table["section_kind"] != section["section_kind"]
            or table["relationship"] != section["relationship"]
            or table["bbox_pt"] != section["bbox_pt"]
            or [table["row_count"], table["column_count"]] != section["shape"]):
        raise ValueError("SECTION_TABLE_BINDING_MISMATCH")
    if len(table["rows"]) != table["row_count"]:
        raise ValueError("INVALID_TABLE_ROW_COUNT")
    for r, row in enumerate(table["rows"]):
        if len(row) != table["column_count"]:
            raise ValueError("INVALID_TABLE_COLUMN_COUNT")
        for c, cell in enumerate(row):
            if cell["row_index"] != r or cell["column_index"] != c:
                raise ValueError("CELL_POSITION_MISMATCH")
    return table


def _check_index(index: dict, source: SourceDocument, as_of: datetime) -> None:
    source.require_available(as_of)
    if index.get("index_schema") != "frp-cn-document-index-candidate-v1":
        raise ValueError("UNKNOWN_INDEX_SCHEMA")
    for k, expected in (
        ("document_id", source.document_id),
        ("source_sha256", source.source_sha256),
        ("canonical_sha256", source.canonical_sha256),
    ):
        if index.get(k) != expected:
            raise ValueError("INDEX_SOURCE_IDENTITY_MISMATCH")
    if (index.get("qualification_status") != "REVIEW_REQUIRED"
            or index.get("financial_semantic_review") != "NOT_PERFORMED"
            or index.get("research_publication") != "BLOCKED"):
        raise ValueError("INDEX_PUBLICATION_BOUNDARY_VIOLATED")
    if len(index.get("pages", [])) != index.get("page_count"):
        raise ValueError("INDEX_PAGE_COUNT_MISMATCH")


def locate_cell_candidate(
    index: dict,
    source: SourceDocument,
    *,
    as_of: datetime,
    section_kind: str,
    row_label: str,
    column_header: str,
) -> dict:
    """Resolve a *single* literal table cell by the root heading and column.

    The column text is a literal header (e.g. ``2026年半年度`` or ``合计``),
    NOT a certified reporting period or scope. The row text is a literal
    source label, NOT a normalized accounting metric. A continuation remains
    a geometric candidate even when a matching cell is found.
    """
    _check_index(index, source, as_of)
    if section_kind not in SECTION_TITLES:
        return _blocked("UNRESOLVED", "UNRECOGNIZED_STATEMENT_TYPE")
    if not row_label.strip() or not column_header.strip():
        return _blocked("UNRESOLVED", "EMPTY_SELECTION")

    entries = [s for s in index["sections"] if s["section_kind"] == section_kind]
    roots = [s for s in entries if s["relationship"] == "SECTION_ROOT_CANDIDATE"]
    if len(roots) != 1:
        return _blocked("UNRESOLVED", "SECTION_ROOT_MISSING_OR_AMBIGUOUS")
    root = roots[0]
    root_table = _index_table(index, root)
    if not root_table["rows"]:
        return _blocked("UNRESOLVED", "ROOT_TABLE_NO_ROWS")
    header = root_table["rows"][0]
    columns = [i for i, c in enumerate(header)
               if isinstance(c["text"], str)
               and _norm(c["text"]) == _norm(column_header)]
    if len(columns) != 1 or columns[0] == 0:
        return _blocked("UNRESOLVED", "COLUMN_HEADER_MISSING_OR_AMBIGUOUS")
    col = columns[0]

    matched = []
    for section in entries:
        if section["relationship"] not in (
            "SECTION_ROOT_CANDIDATE", "GEOMETRIC_CONTINUATION_CANDIDATE"
        ):
            return _blocked("UNRESOLVED", "UNSUPPORTED_SECTION_RELATIONSHIP")
        table = _index_table(index, section)
        if table["column_count"] != root_table["column_count"]:
            return _blocked("UNRESOLVED", "CONTINUATION_COLUMN_MISMATCH")
        for row_i, row in enumerate(table["rows"]):
            if section is root and row_i == 0:
                continue
            label = row[0]["text"]
            if isinstance(label, str) and _norm(label) == _norm(row_label):
                matched.append((section, table, row_i, row))

    if len(matched) != 1:
        return _blocked("UNRESOLVED", (
            "ROW_NOT_FOUND" if not matched else "DUPLICATE_ROW_ACROSS_SECTION"
        ))
    section, table, row_i, row = matched[0]
    cell = row[col]
    if cell["bbox_pt"] is None or row[0]["bbox_pt"] is None:
        return _blocked("UNRESOLVED", "CELL_GEOMETRY_MISSING")
    raw = cell["text"]
    status = "BLANK_OR_UNEXTRACTED" if not isinstance(raw, str) or not raw.strip() else (
        "DASH_UNINTERPRETED" if raw.strip() in _DASHES else "VERBATIM_TEXT"
    )
    identity = "|".join(map(str, (
        source.document_id, source.canonical_sha256, section_kind,
        section["page_number"], section["table_index"], row_i, col,
    )))
    located = {
        "candidate_id": sha256(identity.encode("utf-8")).hexdigest(),
        "document_id": source.document_id,
        "source_url": source.source_url,
        "source_sha256": source.source_sha256,
        "canonical_sha256": source.canonical_sha256,
        "source_report_period": source.report_period,
        "section_kind_candidate": section_kind,
        "section_root_page": root["page_number"],
        "section_relationship": section["relationship"],
        "row_label_verbatim": row[0]["text"],
        "column_header_verbatim": header[col]["text"],
        "cell_text_verbatim": raw,
        "cell_text_status": status,
        "page_number": section["page_number"],
        "table_index": section["table_index"],
        "row_index": row_i,
        "column_index": col,
        "table_bbox_pt": table["bbox_pt"],
        "row_label_bbox_pt": row[0]["bbox_pt"],
        "column_header_bbox_pt": header[col]["bbox_pt"],
        "cell_bbox_pt": cell["bbox_pt"],
        "canonical_text_span": None,
        "source_text_span_status": "NOT_PROVEN_FROM_TABLE_GEOMETRY",
        "accounting_scope_status": "HEADING_CANDIDATE_ONLY",
        "column_meaning_status": "HEADER_TEXT_ONLY",
        "unit_currency_status": "NOT_YET_BOUND",
        "review_status": "REVIEW_REQUIRED",
    }
    return {
        "status": "ONE_CELL_CANDIDATE",
        "reason": "UNREVIEWED_GEOMETRIC_TABLE_CELL",
        "candidates": [located],
        "financial_semantic_review": "NOT_PERFORMED",
        "research_publication": "BLOCKED",
    }


def locate_cells_in_verified_pdf(
    source: SourceDocument,
    pdf_path: Path,
    *,
    as_of: datetime,
    selections: list[dict],
) -> list[dict]:
    """Rebuild one complete source-verified index, then resolve many cells.

    This is an offline development entrypoint. No acceptance reference answers,
    network calls, or GUI code are available to the runtime module.
    """
    index = index_document(source, pdf_path, as_of=as_of)
    results = [locate_cell_candidate(index, source, as_of=as_of, **selection)
               for selection in selections]
    # Capture original statement's printed period/unit/currency context from
    # the root page. Preserve it verbatim; do not interpret or propagate units.
    with pymupdf.open(pdf_path) as pdf:
        for result in results:
            if result["status"] != "ONE_CELL_CANDIDATE":
                continue
            item = result["candidates"][0]
            root_page_no = item["section_root_page"]
            page_info = index["pages"][root_page_no - 1]
            roots = [s for s in index["sections"]
                     if s["section_kind"] == item["section_kind_candidate"]
                     and s["page_number"] == root_page_no
                     and s["relationship"] == "SECTION_ROOT_CANDIDATE"]
            root_table = _index_table(index, roots[0])
            top = root_table["bbox_pt"][1]
            headings = [h for h in page_info["headings"]
                        if h["kind"] == item["section_kind_candidate"]
                        and 0 <= top - h["bbox_pt"][3] <= 145]
            if len(headings) != 1:
                item["statement_context_status"] = "UNRESOLVED_HEADING_CONTEXT"
                item["statement_context_verbatim"] = None
                continue
            heading = headings[0]
            pg = pdf[root_page_no - 1]
            clip = pymupdf.Rect(
                0, heading["bbox_pt"][3] + 0.1, pg.rect.width, top - 0.1
            )
            context = pg.get_text("text", sort=True, clip=clip).strip()
            item["statement_heading_verbatim"] = heading["text"]
            item["statement_context_verbatim"] = context
            item["statement_context_bbox_pt"] = [
                round(float(n), 2) for n in clip
            ]
            item["statement_context_status"] = (
                "VERBATIM_SOURCE_CONTEXT" if context else "EMPTY_CONTEXT"
            )
            item["unit_currency_status"] = "SOURCE_CONTEXT_UNINTERPRETED"
    return results
