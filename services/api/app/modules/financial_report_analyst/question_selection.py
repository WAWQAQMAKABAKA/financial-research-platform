"""M2a: question -> statement -> table rows -> verified cells.

Replaces one document's hardcoded ``SELECTIONS`` with retrieval over the
document's own table vocabulary. No model is called and no new dependency is
added: the statement scope comes from the statement-title contract, the row
labels come from the verified table index, and the reporting column comes from
the manifest reporting period.

This module only *proposes* a selection. It never approves publication: the
caller must still locate the cell, re-check it against the native PDF, and pass
it through ``publication_policy``. An ambiguous or unmatched question yields no
selection, never a best guess.
"""
from __future__ import annotations

from datetime import datetime
import re
import unicodedata

from app.evidence.contracts import SourceDocument
from app.evidence.cell_attribution import _index_table
from app.evidence.document_index import SECTION_TITLES

SELECTION_VERSION = "m2a-question-to-cell-v1"
MAX_FACTS = 3

INCOME_STATEMENT_KINDS = (
    "consolidated_income_statement",
    "parent_income_statement",
)

# Leading enumerations and row prefixes are display scaffolding, not metric
# identity: 一、营业总收入 / 其中：营业收入 / 减：营业成本 / （一）...
_ROW_PREFIX = re.compile(
    r"^(?:[一二三四五六七八九十]+[、.]|[（(][一二三四五六七八九十\d]+[)）]"
    r"|\d+[.、]|其中[:：]|[加减][:：]|注\d*[:：]?)+"
)
# Trailing printed annotations ("（净亏损以“-”号填列）", "(元/股)") are filing
# conventions, not metric identity. They are removed for matching only; the
# located row label always stays verbatim.
_ROW_ANNOTATION = re.compile(r"[（(][^（）()]*[)）]$")
_YEAR = re.compile(r"(?:19|20)\d{2}")

SYNONYM_VERSION = "m2a-synonym-v1"
# Audited and deliberately tiny. Normalization is a candidate-retrieval aid
# only: the selected row label stays verbatim, and publication still requires
# the literal review and the policy. 净利 is intentionally absent because it is
# ambiguous between 净利润 and 归属于母公司股东的净利润.
SYNONYMS = (("营收", "营业收入"),)


def _norm(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value))


def normalize_question(question: str) -> tuple[str, list[dict]]:
    """Apply the audited alias table for matching only."""
    text = _norm(question)
    applied: list[dict] = []
    for alias, canonical in SYNONYMS:
        if alias in text:
            text = text.replace(alias, canonical)
            applied.append({"alias": alias, "canonical": canonical})
    return text, applied


def row_label_core(label: str) -> str:
    """Strip enumeration and trailing filing annotations for matching only."""
    core = _ROW_PREFIX.sub("", _norm(label))
    for _ in range(3):
        stripped = _ROW_ANNOTATION.sub("", core)
        if stripped == core:
            break
        core = stripped
    return core.rstrip(":：").strip()


def _withheld(reason: str, trace: dict) -> dict:
    return {
        "status": "SELECTION_WITHHELD",
        "reason": reason,
        "version": SELECTION_VERSION,
        "statement_kind": None,
        "column_header": None,
        "rows": [],
        "trace": trace,
    }


def _section_pages(index: dict) -> dict[str, set[int]]:
    pages: dict[str, set[int]] = {}
    for section in index.get("sections", []):
        kind = section.get("section_kind")
        if kind in INCOME_STATEMENT_KINDS:
            pages.setdefault(kind, set()).add(section["page_number"])
    return pages


def _row_labels(index: dict, kind: str) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()
    for section in index.get("sections", []):
        if section.get("section_kind") != kind:
            continue
        table = _index_table(index, section)
        is_root = section.get("relationship") == "SECTION_ROOT_CANDIDATE"
        for row_index, row in enumerate(table["rows"]):
            if is_root and row_index == 0:
                continue  # header row
            if not row:
                continue
            label = row[0].get("text")
            if not isinstance(label, str) or not label.strip():
                continue
            key = _norm(label)
            if key in seen:
                continue
            seen.add(key)
            labels.append(label)
    return labels


def _column_available(index: dict, kind: str, column_header: str) -> bool:
    roots = [
        section for section in index.get("sections", [])
        if section.get("section_kind") == kind
        and section.get("relationship") == "SECTION_ROOT_CANDIDATE"
    ]
    if len(roots) != 1:
        return False
    header = _index_table(index, roots[0])["rows"][0]
    matches = [i for i, cell in enumerate(header)
               if _norm(cell.get("text")) == _norm(column_header)]
    return len(matches) == 1 and matches[0] > 0


def _row_matches(index: dict, kind: str, normalized_question: str) -> list[dict]:
    matches = []
    for label in _row_labels(index, kind):
        core = row_label_core(label)
        if len(core) >= 2 and core in normalized_question:
            matches.append({"row_label": label, "core": core, "match_chars": len(core)})
    matches.sort(key=lambda item: (-item["match_chars"], item["row_label"]))
    return matches


def _resolve_statement_scope(
    *,
    question_norm: str,
    present: list[str],
    section_pages: dict[str, set[int]],
    retrieval_hits: list[dict],
    matches_by_kind: dict[str, list[dict]],
) -> tuple[str | None, str | None, str | None]:
    """Title first, then a row that exists in one statement, then retrieval rank."""
    explicit = [kind for kind in present
                if _norm(SECTION_TITLES[kind]) in question_norm]
    if len(explicit) == 1:
        return explicit[0], "QUESTION_STATEMENT_TITLE", None
    if len(explicit) > 1:
        return None, None, "AMBIGUOUS_STATEMENT_SCOPE"

    with_rows = [kind for kind in present if matches_by_kind.get(kind)]
    if len(with_rows) == 1:
        return with_rows[0], "ROW_UNIQUE_STATEMENT", None
    if not with_rows:
        return None, None, "NO_ROW_MATCH"

    weights = {kind: 0.0 for kind in with_rows}
    for rank, hit in enumerate(retrieval_hits):
        page = hit.get("page_number")
        for kind in with_rows:
            if page in section_pages[kind]:
                weights[kind] += 1.0 / (rank + 1)

    ranked = sorted(weights.items(), key=lambda item: -item[1])
    if (ranked and ranked[0][1] > 0
            and (len(ranked) == 1 or ranked[0][1] >= 2 * ranked[1][1])):
        return ranked[0][0], "RETRIEVAL_PAGE_PRIORITY", None
    return None, None, "AMBIGUOUS_STATEMENT_SCOPE"


def select_cells(
    index: dict,
    *,
    question: str,
    report_period: str,
    column_header: str,
    retrieval_hits: list[dict] | None = None,
    forced_statement_kind: str | None = None,
) -> dict:
    """Derive a source-bound selection from the question.

    ``column_header`` is the manifest-derived reporting column. ``retrieval_hits``
    are the ranked canonical-text candidates and are used only to break a
    statement-scope tie; they never select a row.
    """
    question_norm = _norm(question)
    normalized_question, synonyms = normalize_question(question_norm)
    trace: dict = {
        "version": SELECTION_VERSION,
        "question": question,
        "report_period": report_period,
        "column_header": column_header,
        "retrieval_pages": [hit.get("page_number") for hit in (retrieval_hits or [])],
        "row_labels_considered": 0,
        "row_candidates": [],
        "synonyms_applied": synonyms,
        "synonym_version": SYNONYM_VERSION,
        "normalized_question": normalized_question if synonyms else question_norm,
    }

    if not question_norm or len(question) < 2:
        return _withheld("QUESTION_INVALID", trace)

    years = set(_YEAR.findall(question_norm))
    if any(year != report_period[:4] for year in years):
        return _withheld("OUT_OF_PERIOD_SCOPE", trace)

    section_pages = _section_pages(index)
    present = [kind for kind in INCOME_STATEMENT_KINDS if kind in section_pages]
    trace["present_statement_kinds"] = list(present)
    if not present:
        return _withheld("NO_STATEMENT_SCOPE", trace)

    matches_by_kind = {
        kind: _row_matches(index, kind, normalized_question) for kind in present
    }
    trace["row_match_counts"] = {
        kind: len(rows) for kind, rows in matches_by_kind.items()
    }

    if forced_statement_kind is not None:
        if forced_statement_kind not in present:
            return _withheld("NO_STATEMENT_SCOPE", trace)
        kind = forced_statement_kind
        basis = "USER_RESOLVED_STATEMENT_SCOPE"
    else:
        kind, basis, reason = _resolve_statement_scope(
            question_norm=question_norm,
            present=present,
            section_pages=section_pages,
            retrieval_hits=list(retrieval_hits or []),
            matches_by_kind=matches_by_kind,
        )
        if kind is None:
            return _withheld(reason or "NO_STATEMENT_SCOPE", trace)
    trace["statement_kind"] = kind
    trace["statement_title"] = SECTION_TITLES[kind]
    trace["selection_basis"] = basis

    if not _column_available(index, kind, column_header):
        return _withheld("COLUMN_HEADER_UNAVAILABLE", trace)

    labels = _row_labels(index, kind)
    trace["row_labels_considered"] = len(labels)
    matches = matches_by_kind.get(kind, [])

    trace["row_candidates"] = [
        {"row_label": item["row_label"], "core": item["core"]}
        for item in matches
    ]

    # P1: financial metric specificity, not raw string length. A matched row
    # whose core is contained in another matched row's core is a less specific
    # reading of the same question and is dropped. A generic question such as
    # "净利润" still cannot reach "归属于母公司股东的净利润", because that
    # longer core is not contained in the question at all.
    if len(matches) > 1:
        cores = [item["core"] for item in matches]
        kept = [
            item for item in matches
            if not any(item["core"] != other and item["core"] in other for other in cores)
        ]
        dropped = [item["core"] for item in matches if item not in kept]
        trace["specificity_dropped"] = dropped
        matches = kept

    if not matches:
        return _withheld("NO_ROW_MATCH", trace)
    if len(matches) > MAX_FACTS:
        return _withheld("TOO_MANY_ROW_MATCHES", trace)

    return {
        "status": "SELECTION_READY",
        "reason": None,
        "version": SELECTION_VERSION,
        "statement_kind": kind,
        "column_header": column_header,
        "rows": matches,
        "trace": trace,
    }


def validate_candidate(
    item: dict,
    source: SourceDocument,
    *,
    section_kind: str,
    row_label: str,
    column_header: str,
) -> tuple[bool, str]:
    """Re-check one located cell is the one the selection asked for."""
    if not isinstance(item, dict):
        return False, "CANDIDATE_SHAPE_INVALID"
    if (
        item.get("document_id") != source.document_id
        or item.get("source_sha256") != source.source_sha256
        or item.get("canonical_sha256") != source.canonical_sha256
        or item.get("source_url") != source.source_url
    ):
        return False, "CANDIDATE_IDENTITY_MISMATCH"
    if (
        item.get("section_kind_candidate") != section_kind
        or _norm(item.get("row_label_verbatim")) != _norm(row_label)
        or _norm(item.get("column_header_verbatim")) != _norm(column_header)
    ):
        return False, "CANDIDATE_SELECTION_MISMATCH"
    if (
        item.get("source_text_span_status") != "NOT_PROVEN_FROM_TABLE_GEOMETRY"
        or item.get("accounting_scope_status") != "HEADING_CANDIDATE_ONLY"
        or item.get("column_meaning_status") != "HEADER_TEXT_ONLY"
        or item.get("review_status") != "REVIEW_REQUIRED"
    ):
        return False, "CANDIDATE_STATUS_MISMATCH"
    return True, "CANDIDATE_BOUND"
