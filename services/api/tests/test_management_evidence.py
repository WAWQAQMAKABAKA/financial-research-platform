"""M1.8B synthetic management-passage evidence, strictly network-free."""
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.modules.financial_report_analyst import management_evidence as m

AS_OF = datetime(2026, 10, 22, tzinfo=ZoneInfo("Asia/Shanghai"))
PASSAGE = "2026 年上半年公司创新药销售收入 1.23 亿元，同比增长 4.56%，占药品销售收入的比重达 7.89%。"
PAGE = ("二、经营情况的讨论与分析\n1.创新成果持续兑现，创新药销售收入持续增长\n" + PASSAGE)


class FakePage:
    def __init__(self, txt):
        self.txt = txt

    def get_text(self, kind, *, sort=True):
        if kind == "text":
            return self.txt
        if kind == "words":
            return [(0, 0, 10, 10, self.txt, 0, 0, 0)]
        raise ValueError(kind)


class FakePdf:
    def __init__(self, pages):
        self.pages = list(map(FakePage, pages))

    def __enter__(self):
        return self.pages

    def __exit__(self, *args):
        return False


def configure(monkeypatch, tmp_path, pages):
    path = tmp_path / "synthetic.pdf"
    path.write_bytes(b"synthetic-source-not-a-real-pdf")
    source = SimpleNamespace(
        document_id="synthetic-report", canonical_sha256="a" * 64,
        source_sha256=sha256(path.read_bytes()).hexdigest(),
        source_url="https://example.test/synthetic.pdf",
        require_available=lambda t: None,
    )
    monkeypatch.setattr(m.revenue_scope, "SOURCE", source)
    monkeypatch.setattr(m.pymupdf, "open", lambda p: FakePdf(pages))
    return path


def test_unique_passage_has_source_binding_and_no_semantic_admit(monkeypatch, tmp_path):
    path = configure(monkeypatch, tmp_path, ["other material", PAGE])
    answer = m.locate_management_excerpt(path, as_of=AS_OF)
    assert answer["status"] == "SOURCE_PASSAGE_REVIEWED"
    assert answer["source_page"] == 2
    assert answer["evidence_id"] and len(answer["evidence_id"]) == 64
    assert answer["passage_whitespace_normalized"] == m._norm(PASSAGE)
    assert answer["review_scope"] == "NATIVE_PDF_TEXT_AND_WORD_LOCATION_ONLY"
    assert answer["financial_semantic_review"] == "NOT_PERFORMED"
    assert answer["research_publication"] == "BLOCKED"


def test_duplicate_passage_withheld(monkeypatch, tmp_path):
    path = configure(monkeypatch, tmp_path, [PAGE, PAGE])
    with pytest.raises(ValueError, match="NOT_UNIQUE"):
        m.locate_management_excerpt(path, as_of=AS_OF)


def test_bogus_document_change_rejected(monkeypatch, tmp_path):
    path = configure(monkeypatch, tmp_path, [PAGE])
    path.write_bytes(b"modified")
    with pytest.raises(ValueError, match="SOURCE_SHA_MISMATCH"):
        m.locate_management_excerpt(path, as_of=AS_OF)


def test_wrong_section_and_broken_word_text_fail_closed(monkeypatch, tmp_path):
    path = configure(monkeypatch, tmp_path, [PASSAGE])
    with pytest.raises(ValueError, match="NOT_UNIQUE"):
        m.locate_management_excerpt(path, as_of=AS_OF)
    path = configure(monkeypatch, tmp_path, [PAGE])
    class MismatchedPage(FakePage):
        def get_text(self, kind, *, sort=True):
            if kind == "words":
                return [(0, 0, 10, 10, "inconsistent words", 0, 0, 0)]
            return super().get_text(kind, sort=sort)
    class NativeMismatch:
        def __enter__(self):
            return [MismatchedPage(PAGE)]
        def __exit__(self, *args):
            return False
    monkeypatch.setattr(m.pymupdf, "open", lambda p: NativeMismatch())
    with pytest.raises(ValueError, match="NATIVE_TEXT_LOCATION_MISMATCH"):
        m.locate_management_excerpt(path, as_of=AS_OF)
