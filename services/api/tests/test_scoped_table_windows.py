"""M117 synthetic scoped-window structural and fail-closed tests.

No protected GT, company values, expected financial answers or network.
"""
from datetime import date, datetime
from hashlib import sha256
from zoneinfo import ZoneInfo

import pymupdf
import pytest

from app.evidence import document_index
from app.evidence.cell_attribution import _check_index
from app.evidence.contracts import SourceDocument
from app.evidence.pdf_canonicalizer import canonicalize_pdf

WHEN = datetime(
    2026, 10, 24, tzinfo=ZoneInfo("Asia/Shanghai"),
)

CON = "consolidated_income_statement"
PAR = "parent_income_statement"
CASH = "consolidated_cash_flow"


def h(kind, y=100):
    return {
        "kind": kind,
        "text": kind,
        "bbox_pt": [50.0, y, 200.0, y + 15.0],
    }


def headings():
    return [
        [],
        [h(CON)],
        [],
        [h(PAR)],
        [h(CASH)],
        [],
    ]


def test_scoped_windows_keep_shared_boundary_pages():
    found = document_index.scoped_table_pages(
        headings(),
        frozenset({CON, PAR}),
    )
    assert found == {1, 2, 3, 4}
    assert 0 not in found
    assert 5 not in found


def test_duplicate_target_heading_rejected():
    data = headings()
    data[2] = [h(CON)]

    with pytest.raises(
        ValueError, match="SCOPED_SECTION_HEADING_AMBIGUOUS",
    ):
        document_index.scoped_table_pages(
            data, frozenset({CON}),
        )


def test_missing_target_heading_rejected():
    with pytest.raises(
        ValueError, match="SCOPED_SECTION_HEADING_AMBIGUOUS",
    ):
        document_index.scoped_table_pages(
            headings(), frozenset({"parent_balance_sheet"}),
        )


def test_missing_terminal_boundary_rejected():
    with pytest.raises(
        ValueError, match="SCOPED_SECTION_BOUNDARY_MISSING",
    ):
        document_index.scoped_table_pages(
            [[h(CON)], [], []],
            frozenset({CON}),
        )


def test_unbounded_window_rejected():
    data = [[h(CON)]] + [[] for _ in range(18)] + [[h(CASH)]]

    with pytest.raises(
        ValueError, match="SCOPED_SECTION_WINDOW_UNBOUNDED",
    ):
        document_index.scoped_table_pages(
            data, frozenset({CON}),
        )


def source_fixture(tmp_path):
    path = tmp_path / "synthetic.pdf"

    with pymupdf.open() as doc:
        for _ in range(6):
            doc.new_page()
        doc.save(path)

    digest = sha256(path.read_bytes()).hexdigest()

    canonical = canonicalize_pdf(
        document_id="SYNTHETIC-SCOPED",
        pdf_path=path,
        expected_source_sha256=digest,
    )

    source = SourceDocument(
        document_id="SYNTHETIC-SCOPED",
        ticker="SYN",
        report_period="2026H1",
        source_url="https://example.invalid/scoped.pdf",
        published_on=date(2026, 8, 20),
        source_sha256=digest,
        canonical_sha256=canonical.canonical_sha256,
    )

    return path, source


def test_scoped_index_all_pages_discovered_tables_bounded(
    tmp_path, monkeypatch,
):
    path, source = source_fixture(tmp_path)
    discovered = headings()
    table_calls = []

    monkeypatch.setattr(
        document_index,
        "headings_on_page",
        lambda page: discovered[page.number],
    )

    def count_tables(page):
        table_calls.append(page.number)
        return []

    monkeypatch.setattr(
        document_index, "_tables_on_page", count_tables,
    )

    result = document_index.index_document_scoped(
        source, path,
        as_of=WHEN,
        section_kinds=frozenset({CON, PAR}),
    )

    assert table_calls == [1, 2, 3, 4]
    assert len(result["pages"]) == 6

    coverage = result["table_extraction_coverage"]

    assert coverage["mode"] == "SECTION_WINDOW"
    assert coverage["requested_section_kinds"] == [CON, PAR]
    assert coverage["scanned_pages"] == [2, 3, 4, 5]
    assert coverage["heading_pages_scanned"] == 6
    assert result["research_publication"] == "BLOCKED"
    assert result["financial_semantic_review"] == "NOT_PERFORMED"

    _check_index(result, source, WHEN)

    result["table_extraction_coverage"]["scanned_pages"] = [2, 3]

    with pytest.raises(
        ValueError, match="SCOPED_INDEX_PAGES_MISMATCH",
    ):
        _check_index(result, source, WHEN)


def test_scoped_index_cannot_hide_out_of_window_tables(
    tmp_path, monkeypatch,
):
    path, source = source_fixture(tmp_path)
    discovered = headings()

    monkeypatch.setattr(
        document_index,
        "headings_on_page",
        lambda page: discovered[page.number],
    )
    monkeypatch.setattr(
        document_index,
        "_tables_on_page",
        lambda page: [],
    )

    result = document_index.index_document_scoped(
        source, path,
        as_of=WHEN,
        section_kinds=frozenset({CON}),
    )

    # Simulate an incorrectly populated out-of-window page.
    result["pages"][0]["tables"] = [{"table_index": 0}]

    with pytest.raises(
        ValueError, match="SCOPED_INDEX_TABLE_OUTSIDE_WINDOW",
    ):
        _check_index(result, source, WHEN)


def test_scoped_index_wrong_source_hash_fails(
    tmp_path,
):
    path, source = source_fixture(tmp_path)
    wrong = source.model_copy(
        update={"source_sha256": "0" * 64}
    )

    with pytest.raises(ValueError, match="SOURCE_SHA_MISMATCH"):
        document_index.index_document_scoped(
            wrong, path,
            as_of=WHEN,
            section_kinds=frozenset({CON}),
        )
