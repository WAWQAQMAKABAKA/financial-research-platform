from datetime import date, datetime, time, timedelta
from typing import Sequence
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator


SHANGHAI = ZoneInfo("Asia/Shanghai")


class StrictRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceDocument(StrictRecord):
    document_id: str = Field(min_length=1)
    ticker: str = Field(min_length=1)
    report_period: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    published_on: date
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    canonical_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @property
    def pit_available_at(self) -> datetime:
        return datetime.combine(
            self.published_on + timedelta(days=1),
            time.min,
            tzinfo=SHANGHAI,
        )

    def require_available(self, as_of: datetime) -> None:
        if as_of.utcoffset() is None:
            raise ValueError("PIT_AS_OF_MUST_BE_TIMEZONE_AWARE")

        if as_of.astimezone(SHANGHAI) < self.pit_available_at:
            raise ValueError("PIT_UNAVAILABLE")


class EvidenceSpan(StrictRecord):
    evidence_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    canonical_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    page_number: int = Field(ge=1)
    canonical_start: int = Field(ge=0)
    canonical_end: int = Field(gt=0)
    excerpt: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_span(self):
        if self.canonical_end <= self.canonical_start:
            raise ValueError("INVALID_CANONICAL_SPAN")
        return self


def require_evidence_binding(
    source: SourceDocument,
    evidence: EvidenceSpan,
    as_of: datetime,
) -> None:
    source.require_available(as_of)

    if evidence.document_id != source.document_id:
        raise ValueError("EVIDENCE_DOCUMENT_MISMATCH")

    if evidence.canonical_sha256 != source.canonical_sha256:
        raise ValueError("EVIDENCE_CANONICAL_HASH_MISMATCH")


def require_claim_evidence(
    source: SourceDocument,
    evidence_items: Sequence[EvidenceSpan],
    evidence_ids: Sequence[str],
    as_of: datetime,
) -> None:
    source.require_available(as_of)

    index = {item.evidence_id: item for item in evidence_items}

    if len(index) != len(evidence_items):
        raise ValueError("DUPLICATE_EVIDENCE_ID")

    for evidence_id in evidence_ids:
        item = index.get(evidence_id)

        if item is None:
            raise ValueError("UNKNOWN_EVIDENCE_ID")

        require_evidence_binding(source, item, as_of)
