"""M123 offline source-heading context diagnostics; synthetic canonical spans only."""
from datetime import date, datetime
from hashlib import sha256
from zoneinfo import ZoneInfo

import pytest

from app.evidence.contracts import SourceDocument
from app.evidence.pdf_canonicalizer import CanonicalDocument, CanonicalPage
from app.modules.financial_report_analyst.source_context import (
    CONTEXT_VERSION, attach_heading_context,
)
from app.modules.financial_report_analyst.canonical_retrieval import retrieve_from_canonical

WHEN = datetime(2026, 10, 25, tzinfo=ZoneInfo("Asia/Shanghai"))


def fixture():
    bodies = (
        "公司财务报表\n合并现金流量表\n经营活动产生的现金流量净额 100.00\n",
        "经营活动产生的现金流量净额 101.00\n母公司现金流量表\n经营活动产生的现金流量净额 200.00\n",
        "经营活动产生的现金流量净额 201.00\n",
        "经营活动产生的现金流量净额 202.00\n",
        "公司解释合并现金流量表列示的指标，文字并非独立标题。\n",
    )
    parts, pages = [], []
    offset = 0
    for number, body in enumerate(bodies, 1):
        marker = f"=== PAGE {number} ===\n"
        pages.append(CanonicalPage(number, offset, offset + len(marker), offset + len(marker) + len(body)))
        parts.append(marker + body + "\n")
        offset += len(marker) + len(body) + 1
    txt = "".join(parts)
    source = SourceDocument(
        document_id="synthetic-m123", ticker="TEST", report_period="2026H1",
        source_url="https://example.invalid/source.pdf", published_on=date(2026, 8, 20),
        source_sha256="a" * 64, canonical_sha256=sha256(txt.encode()).hexdigest(),
    )
    doc = CanonicalDocument(source.document_id, source.source_sha256, source.canonical_sha256,
                            txt, tuple(pages))
    return source, doc


def hit(doc, page, snippet):
    body = doc.pages[page - 1]
    position = doc.canonical_text.find(snippet, body.content_start, body.content_end)
    assert position >= 0
    return {
        "source_page": page, "canonical_start": position,
        "canonical_end": position + len(snippet), "source_excerpt": snippet,
        "evidence_id": "synthetic",
    }


def test_same_page_heading_cue_exact_canonical_coordinates():
    _, doc = fixture()
    evidence, alert = attach_heading_context(doc, [hit(doc, 1, "经营活动产生的现金流量净额 100.00")])
    cue = evidence[0]["statement_heading_cue"]
    assert cue["status"] == "STANDALONE_HEADING_CANDIDATE"
    assert cue["heading_verbatim"] == "合并现金流量表"
    assert doc.canonical_text[cue["heading_start"]:cue["heading_end"]] == cue["heading_verbatim"]
    assert cue["heading_page"] == 1
    assert alert == "NOT_ASSESSED"  # NOT_ASSESSED does not mean certified safe.


def test_preceding_page_heading_inheritance_bounded():
    _, doc = fixture()
    evidence, _ = attach_heading_context(doc, [hit(doc, 2, "经营活动产生的现金流量净额 101.00")])
    assert evidence[0]["statement_heading_cue"]["heading_verbatim"] == "合并现金流量表"


def test_second_statement_heading_and_mixed_scope_alert():
    _, doc = fixture()
    evidence, alert = attach_heading_context(doc, [
        hit(doc, 1, "经营活动产生的现金流量净额 100.00"),
        hit(doc, 2, "经营活动产生的现金流量净额 200.00"),
    ])
    assert [e["statement_heading_cue"]["heading_verbatim"] for e in evidence] == [
        "合并现金流量表", "母公司现金流量表",
    ]
    assert alert == "MULTIPLE_STATEMENT_HEADING_CANDIDATES"


def test_scope_unresolved_if_heading_in_chunk_or_more_than_previous_page():
    _, doc = fixture()
    first = hit(doc, 2, "母公司现金流量表\n经营活动产生的现金流量净额 200.00")
    far = hit(doc, 4, "经营活动产生的现金流量净额 202.00")
    evidence, _ = attach_heading_context(doc, [first, far])
    assert all(e["statement_heading_cue"]["status"] == "UNRESOLVED" for e in evidence)
    assert all(e["statement_heading_cue"]["heading_verbatim"] is None for e in evidence)


def test_in_line_prose_never_becomes_heading():
    _, doc = fixture()
    item = hit(doc, 5, "公司解释合并现金流量表列示的指标，文字并非独立标题。")
    evidence, _ = attach_heading_context(doc, [item])
    assert evidence[0]["statement_heading_cue"]["status"] == "UNRESOLVED"


def test_bad_evidence_coordinates_fail_closed():
    _, doc = fixture()
    item = hit(doc, 1, "经营活动产生的现金流量净额 100.00")
    for field, changed in [("source_page", 2), ("canonical_start", 999999),
                           ("source_excerpt", "different")]:
        with pytest.raises(ValueError, match="HEADING_CUE_EVIDENCE_SPAN_INVALID"):
            attach_heading_context(doc, [{**item, field: changed}])


def test_retrieval_interface_preserves_source_only_state():
    source, doc = fixture()
    packet = retrieve_from_canonical(source, doc, "现金流量净额", as_of=WHEN)
    assert packet["context_probe_version"] == CONTEXT_VERSION
    assert packet["retrieval_context_review"] == "HEADING_CUE_ONLY_NOT_SEMANTICALLY_REVIEWED"
    assert packet["statement_heading_alert"] in (
        "NOT_ASSESSED", "MULTIPLE_STATEMENT_HEADING_CANDIDATES")
    assert packet["research_publication"] == "BLOCKED"
    assert packet["financial_semantic_review"] == "NOT_PERFORMED"
    assert packet["report_storage"] == "NOT_PERSISTED"
    assert packet["evidence"]
    assert all("statement_heading_cue" in e for e in packet["evidence"])
