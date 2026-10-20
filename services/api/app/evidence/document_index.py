"""Full-document Chinese financial PDF *candidate* index.

This is an offline structural-ingestion component, not a financial interpreter.
Uses the existing PyMuPDF API. Never receives financial answer labels, page hints,
or category-specific amounts. Section names are a reusable discovery vocabulary.
No API route, agent, or publication authority is provided by this module.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
import unicodedata

import pymupdf

from app.evidence.contracts import SourceDocument
from app.evidence.pdf_canonicalizer import canonicalize_pdf


PARSER_ID = "frp-cn-full-document-structure"
PARSER_VERSION = "0.1.0"

# These are accounting statement *types*, not issuer-specific pages or values.
# Adding aliases requires development qualification, not benchmark-answer tuning.
SECTION_TITLES = {
    "consolidated_balance_sheet": "合并资产负债表",
    "parent_balance_sheet": "母公司资产负债表",
    "consolidated_income_statement": "合并利润表",
    "parent_income_statement": "母公司利润表",
    "consolidated_cash_flow": "合并现金流量表",
    "parent_cash_flow": "母公司现金流量表",
    "segment_financial_information": "报告分部的财务信息",
}


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value))


def _rect(value) -> list[float] | None:
    if value is None:
        return None
    return [round(float(n), 2) for n in value]


def classify_heading(text: str) -> str | None:
    """Only isolated title lines, never mentions embedded in paragraphs."""
    norm = _compact(text)
    for kind, title in SECTION_TITLES.items():
        if kind == "segment_financial_information":
            # Section enumeration varies by issuer; title remains a vocabulary.
            if re.fullmatch(r"(?:[（(]?\d{1,2}[)）.、]?)?" + title, norm):
                return kind
        elif norm == title:
            return kind
    return None


def headings_on_page(page) -> list[dict]:
    result = []
    for block in page.get_text("dict")["blocks"]:
        if "lines" not in block:
            continue
        for line in block["lines"]:
            words = [span["text"] for span in line["spans"]]
            kind = classify_heading("".join(words))
            if kind:
                result.append({"kind": kind, "text": "".join(words),
                               "bbox_pt": _rect(line["bbox"])})
    # A repeated rendered heading should not produce duplicate boundaries.
    dedup = {}
    for h in result:
        key = (h["kind"], round(h["bbox_pt"][1], 1))
        dedup.setdefault(key, h)
    return sorted(dedup.values(), key=lambda h: h["bbox_pt"][1])


def _extract_table(table, table_index: int, strategy: str) -> dict:
    raw = table.extract()
    if len(raw) != table.row_count or len(table.rows) != table.row_count:
        raise ValueError("INCONSISTENT_TABLE_ROWS")
    rows = []
    for i, row in enumerate(raw):
        if len(row) != table.col_count or len(table.rows[i].cells) != table.col_count:
            raise ValueError("INCONSISTENT_TABLE_COLUMNS")
        cells = []
        for j, text in enumerate(row):
            cells.append({
                "row_index": i,
                "column_index": j,
                "text": text,  # None and empty strings are not interpreted as zero.
                "bbox_pt": _rect(table.rows[i].cells[j]),
                "extraction_status": (
                    "TEXT_DETECTED" if text and text.strip() else "BLANK_OR_UNEXTRACTED"
                ),
            })
        rows.append(cells)
    return {
        "table_index": table_index,
        "bbox_pt": _rect(table.bbox),
        "row_count": table.row_count,
        "column_count": table.col_count,
        "strategy": strategy,
        "rows": rows,
        "section_kind": None,
        "relationship": "UNASSIGNED",
        "review_status": "REVIEW_REQUIRED",
    }


def _tables_on_page(page) -> list[dict]:
    # First strategy preserves drawn ruled grids; one fallback for non-strict lines.
    for strategy in ("lines_strict", "lines"):
        tables = page.find_tables(strategy=strategy).tables
        if tables:
            return sorted((_extract_table(t, i, strategy) for i, t in enumerate(tables)),
                          key=lambda t: (t["bbox_pt"][1], t["bbox_pt"][0]))
    return []


def _grid_compatible(old: dict, new: dict, page_width: float) -> bool:
    if old["column_count"] != new["column_count"]:
        return False
    tolerance = max(12.0, page_width * 0.026)
    if (abs(old["bbox_pt"][0] - new["bbox_pt"][0]) > tolerance or
            abs(old["bbox_pt"][2] - new["bbox_pt"][2]) > tolerance):
        return False

    def right_edges(tbl: dict) -> list[float] | None:
        for row in tbl["rows"][:4]:
            if all(cell["bbox_pt"] is not None for cell in row):
                return [cell["bbox_pt"][2] for cell in row[:-1]]
        return None

    a, b = right_edges(old), right_edges(new)
    return (a is None or b is None or (len(a) == len(b) and
            all(abs(x - y) <= tolerance for x, y in zip(a, b))))


def assign_sections(pages: list[dict]) -> None:
    """Label structural *candidates*; never claim semantic section certainty.

    A second heading halfway down a page starts a new section region. Earlier
    rows on that page may still be a continuation of the previous section.
    """
    previous: tuple[str, dict, int, float] | None = None
    for page in pages:
        height = page["height_pt"]
        width = page["width_pt"]
        headings = page["headings"]
        used_headings: set[int] = set()
        last_on_page: tuple[str, dict, int, float] | None = None
        for table in page["tables"]:
            top = table["bbox_pt"][1]
            # Only headings *above* a table are candidates. A heading printed
            # below a continued table cannot relabel the preceding cells.
            eligible = [(i, h) for i, h in enumerate(headings)
                        if i not in used_headings and
                        -2 <= top - h["bbox_pt"][3] <= min(145, height * 0.22) and
                        table["bbox_pt"][0] <= h["bbox_pt"][2] + width * .1 and
                        table["bbox_pt"][2] >= h["bbox_pt"][0]]
            if eligible:
                i, h = max(eligible, key=lambda x: x[1]["bbox_pt"][3])
                used_headings.add(i)
                table["section_kind"] = h["kind"]
                table["relationship"] = "SECTION_ROOT_CANDIDATE"
                previous = (h["kind"], table, page["page_number"], height)
                last_on_page = previous
                continue

            predecessor = last_on_page or previous
            if predecessor is None:
                continue
            kind, prev_table, prev_page, prev_height = predecessor
            # If a different section starts between the predecessor table and
            # this table, never carry its column identity across the boundary.
            if any(prev_table["bbox_pt"][1] < h["bbox_pt"][1] < top
                   for h in headings if prev_page == page["page_number"]):
                continue
            if prev_page == page["page_number"]:
                # Multiple sub-tables on the same page are not silently merged.
                continue
            if prev_page != page["page_number"] - 1:
                continue
            if prev_table["bbox_pt"][3] < prev_height * .70:
                continue
            if top > height * .30 or not _grid_compatible(prev_table, table, width):
                continue
            table["section_kind"] = kind
            table["relationship"] = "GEOMETRIC_CONTINUATION_CANDIDATE"
            last_on_page = (kind, table, page["page_number"], height)
            previous = last_on_page
        if last_on_page is None:
            # Do not bridge pages without a table, including accounting prose.
            previous = None


def index_document(source: SourceDocument, pdf_path: Path, *, as_of: datetime) -> dict:
    """Verify source identity and conservatively index *all* PDF pages.

    The resulting structure is NOT certified CAS semantics or a publishable
    research report. Do not import this into customer runtime without review.
    """
    source.require_available(as_of)
    canonical = canonicalize_pdf(
        document_id=source.document_id,
        pdf_path=pdf_path,
        expected_source_sha256=source.source_sha256,
    )
    if canonical.canonical_sha256 != source.canonical_sha256:
        raise ValueError("CANONICAL_SHA_MISMATCH")

    pages = []
    with pymupdf.open(pdf_path) as doc:
        for index in range(len(doc)):
            page = doc[index]
            record = {
                "page_number": index + 1,
                "width_pt": round(page.rect.width, 2),
                "height_pt": round(page.rect.height, 2),
                "headings": headings_on_page(page),
                "tables": _tables_on_page(page),
            }
            pages.append(record)

    assign_sections(pages)
    assigned = [
        {"page_number": page["page_number"], "table_index": table["table_index"],
         "section_kind": table["section_kind"], "relationship": table["relationship"],
         "bbox_pt": table["bbox_pt"], "shape": [table["row_count"], table["column_count"]]}
        for page in pages for table in page["tables"] if table["section_kind"]
    ]
    return {
        "index_schema": "frp-cn-document-index-candidate-v1",
        "parser_id": PARSER_ID,
        "parser_version": PARSER_VERSION,
        "document_id": source.document_id,
        "source_url": source.source_url,
        "source_sha256": source.source_sha256,
        "canonical_sha256": source.canonical_sha256,
        "checked_as_of": as_of.isoformat(),
        "page_count": len(pages),
        "sections": assigned,
        "pages": pages,
        "qualification_status": "REVIEW_REQUIRED",
        "financial_semantic_review": "NOT_PERFORMED",
        "research_publication": "BLOCKED",
    }
