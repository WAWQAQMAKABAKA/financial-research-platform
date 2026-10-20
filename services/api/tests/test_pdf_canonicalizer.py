from hashlib import sha256

import pymupdf
import pytest

from app.evidence.pdf_canonicalizer import canonicalize_pdf


def make_pdf(tmp_path):
    path = tmp_path / "synthetic.pdf"

    with pymupdf.open() as pdf:
        for body in (
            "REPORT HEADER\nAlpha\n1 / 2",
            "REPORT HEADER\nBeta\n2 / 2",
        ):
            page = pdf.new_page()
            page.insert_text((72, 72), body)
        pdf.save(path)

    return path


def parse(path):
    return canonicalize_pdf(
        document_id="SYNTHETIC",
        pdf_path=path,
        expected_source_sha256=sha256(
            path.read_bytes()
        ).hexdigest(),
    )


def test_page_offsets_and_header_removal(tmp_path):
    result = parse(make_pdf(tmp_path))

    assert result.canonical_text == (
        "=== PAGE 1 ===\nREPORT HEADER\nAlpha\n"
        "=== PAGE 2 ===\nBeta\n"
    )

    assert len(result.pages) == 2

    for page in result.pages:
        marker = f"=== PAGE {page.page_number} ==="

        assert result.canonical_text[
            page.marker_start:
            page.marker_start + len(marker)
        ] == marker

        assert page.marker_start < page.content_start
        assert page.content_start <= page.content_end


def test_deterministic_canonical_hash(tmp_path):
    path = make_pdf(tmp_path)
    first = parse(path)
    second = parse(path)

    assert first.canonical_sha256 == second.canonical_sha256
    assert first.pages == second.pages
    assert first.parser_version == "1"


def test_reject_html_response(tmp_path):
    path = tmp_path / "response.pdf"
    path.write_bytes(b"<html>Not a PDF</html>")

    with pytest.raises(ValueError, match="SOURCE_NOT_PDF"):
        parse(path)


def test_reject_source_hash_mismatch(tmp_path):
    path = make_pdf(tmp_path)

    with pytest.raises(ValueError, match="SOURCE_SHA_MISMATCH"):
        canonicalize_pdf(
            document_id="SYNTHETIC",
            pdf_path=path,
            expected_source_sha256="0" * 64,
        )
