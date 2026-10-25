"""M118B: financial-question interpretation proposal contract.

A structurally valid proposal is NOT a correct interpretation.
This module performs no retrieval, accounting review, LLM call,
answer generation, trading, persistence, or publication.
"""
from __future__ import annotations

from enum import StrEnum
from hashlib import sha256
from typing import Literal

from pydantic import Field, computed_field, model_validator

from app.evidence.contracts import StrictRecord


class QuestionOperation(StrEnum):
    LOOKUP = "LOOKUP"
    RATIO = "RATIO"
    COMPARE = "COMPARE"
    EXPLAIN = "EXPLAIN"
    VERIFY = "VERIFY"
    LOCATE_SOURCE = "LOCATE_SOURCE"
    FORECAST = "FORECAST"
    TRADE_ACTION = "TRADE_ACTION"
    UNKNOWN = "UNKNOWN"


class QuestionIntentProposal(StrictRecord):
    """Untrusted candidate meaning of one exact customer question."""

    question: str = Field(min_length=1, max_length=240)

    operation_candidate: QuestionOperation

    metric_candidate: str | None = Field(
        default=None, min_length=1
    )
    numerator_candidate: str | None = Field(
        default=None, min_length=1
    )
    denominator_candidate: str | None = Field(
        default=None, min_length=1
    )

    issuer_candidate: str | None = Field(
        default=None, min_length=1
    )
    period_candidate: str | None = Field(
        default=None, min_length=1
    )
    reporting_scope_candidate: str | None = Field(
        default=None, min_length=1
    )

    unresolved: tuple[str, ...] = ()

    interpretation_status: Literal[
        "UNVERIFIED_PROPOSAL"
    ] = "UNVERIFIED_PROPOSAL"

    financial_semantic_review: Literal[
        "NOT_PERFORMED"
    ] = "NOT_PERFORMED"

    research_publication: Literal[
        "BLOCKED"
    ] = "BLOCKED"

    @computed_field
    @property
    def question_sha256(self) -> str:
        return sha256(
            self.question.encode("utf-8")
        ).hexdigest()

    @model_validator(mode="after")
    def reject_incoherent_shapes(self):
        if not self.question.strip():
            raise ValueError("EMPTY_QUESTION")

        if any(
            not item.strip()
            for item in self.unresolved
        ):
            raise ValueError("EMPTY_UNRESOLVED_REASON")

        if self.operation_candidate is QuestionOperation.RATIO:
            if (
                self.denominator_candidate is None
                and not self.unresolved
            ):
                raise ValueError(
                    "RATIO_DENOMINATOR_UNRESOLVED"
                )

        if self.operation_candidate is QuestionOperation.UNKNOWN:
            if not self.unresolved:
                raise ValueError(
                    "UNKNOWN_OPERATION_MUST_BE_EXPLICIT"
                )

        return self
