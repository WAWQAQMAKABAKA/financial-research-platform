"""Deterministic native-text PDF canonicalization.

Algorithm reference:
WAWQAQMAKABAKA/quant-desk, lab/retrieval-v1,
labs/retrieval_lab/src/retrieval_lab/parsing/pdf_canonicalizer.py
Git blob: c262ff9126aa3ed0745552d9d107c60e7f7c7003

Native implementation. No legacy runtime imports.
"""

from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
from math import ceil
from pathlib import Path
import re

import pymupdf


_FOOTER = re.compile(r"^\s*\d+\s*/\s*\d+\s*$")


@dataclass(frozen=True)
class CanonicalPage:
    page_number: int
    marker_start: int
    content_start: int
    content_end: int


@dataclass(frozen=True)
class CanonicalDocument:
    document_id: str
    source_sha256: str
    canonical_sha256: str
    canonical_text: str
    pages: tuple[CanonicalPage, ...]
    parser_id: str = "pymupdf-native-canonicalizer"
    parser_version: str = "1"


def _lines(text: str) -> list[str]:
    text = (
        text.replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\x00", "")
    )
    result = []
    prev_blank = False

    for line in (part.rstrip() for part in text.split("\n")):
        blank = not line.strip()
        if not (blank and prev_blank):
            result.append(line)
        prev_blank = blank

    while result and not result[-1].strip():
        result.pop()

    return result


def _nonempty(
    lines: list[str],
    reverse: bool = False,
) -> tuple[int, str] | None:
    indices = (
        range(len(lines) - 1, -1, -1)
        if reverse
        else range(len(lines))
    )

    for index in indices:
        if lines[index].strip():
            return index, lines[index].strip()

    return None


def canonicalize_pdf(
    *,
    document_id: str,
    pdf_path: Path,
    expected_source_sha256: str,
) -> CanonicalDocument:
    raw = pdf_path.read_bytes()

    if not raw.startswith(b"%PDF-"):
        raise ValueError("SOURCE_NOT_PDF")

    source_hash = sha256(raw).hexdigest()

    if source_hash != expected_source_sha256:
        raise ValueError("SOURCE_SHA_MISMATCH")

    with pymupdf.open(pdf_path) as pdf:
        if (
            not pdf.is_pdf
            or pdf.needs_pass
            or pdf.page_count < 1
        ):
            raise ValueError("SOURCE_PDF_UNUSABLE")

        pages = [
            _lines(
                pdf.load_page(i).get_text(
                    "text",
                    sort=True,
                )
            )
            for i in range(pdf.page_count)
        ]

    first_lines = [
        found[1]
        for lines in pages
        if (found := _nonempty(lines)) is not None
    ]

    counts = Counter(first_lines)
    min_count = max(2, ceil(len(pages) * 0.60))

    headers = {
        line
        for line, count in counts.items()
        if count >= min_count
    }

    pieces = []
    page_records = []
    cursor = 0

    for number, original in enumerate(pages, start=1):
        lines = list(original)

        first = _nonempty(lines)

        if number > 1 and first and first[1] in headers:
            del lines[first[0]]

        last = _nonempty(lines, reverse=True)

        if last and _FOOTER.fullmatch(last[1]):
            del lines[last[0]]

        while lines and not lines[-1].strip():
            lines.pop()

        body = "\n".join(lines)
        marker = f"=== PAGE {number} ==="

        page_records.append(
            CanonicalPage(
                page_number=number,
                marker_start=cursor,
                content_start=cursor + len(marker) + 1,
                content_end=cursor + len(marker) + 1 + len(body),
            )
        )

        pieces.append(marker + "\n" + body + "\n")
        cursor += len(marker) + 1 + len(body) + 1

    canonical_text = "".join(pieces)

    return CanonicalDocument(
        document_id=document_id,
        source_sha256=source_hash,
        canonical_sha256=sha256(
            canonical_text.encode("utf-8")
        ).hexdigest(),
        canonical_text=canonical_text,
        pages=tuple(page_records),
    )
