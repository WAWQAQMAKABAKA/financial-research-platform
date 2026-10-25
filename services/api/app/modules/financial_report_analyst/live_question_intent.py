"""M119A: one bounded, development-only DeepSeek question-intent adapter.

An LLM proposal is not source evidence, financial-semantic approval, or a
research answer. No evaluation labels, PDF text, trading data, or publication.
"""
from __future__ import annotations

import os
import re
import unicodedata

import httpx
from pydantic import BaseModel, ConfigDict

from app.modules.financial_report_analyst import deepseek_draft
from app.modules.financial_report_analyst.question_intent import (
    QuestionIntentProposal,
    QuestionOperation,
)

MODEL = "deepseek-flash"
REPORT_KEY = "600276-2026H1"

# Retain the same prompt used for the 40-question development baseline.
SYSTEM = """
You interpret the customer's financial research question.
Identify WHAT the customer asks, not the financial answer.

Operation meanings:
LOOKUP = obtain a disclosed fact or value.
RATIO = find a share or percentage of a denominator.
COMPARE = compare metrics, periods, or changes.
EXPLAIN = seek causes or reasons.
VERIFY = check whether a financial assertion is true.
LOCATE_SOURCE = locate the original disclosure.
FORECAST = ask about future financial outcomes.
TRADE_ACTION = request a trading decision or position.
UNKNOWN = the requested operation cannot be determined.

Missing evidence does NOT make question intent UNKNOWN.
Preserve explicit numerator, denominator and reporting scope.
Do not equate drug sales with consolidated company revenue.
If a denominator is absent, use null and note the ambiguity.
Do not invent data, retrieve evidence, calculate, or give advice.

Return ONLY valid JSON, with exactly these six fields:
operation, metric, numerator, denominator,
reporting_scope, unresolved.

Example JSON format (illustrative only):
{"operation":"COMPARE","metric":"example metric",
"numerator":null,"denominator":null,
"reporting_scope":null,"unresolved":[]}
"""


class CompactIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: QuestionOperation
    metric: str | None
    numerator: str | None
    denominator: str | None
    reporting_scope: str | None
    unresolved: list[str]


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value)).casefold()


def in_current_source_scope(question: str) -> bool:
    """Narrow paid-call allowlist; NOT proof of financial/accounting meaning."""
    if not isinstance(question, str) or len(question) > 240:
        return False
    if len(question.encode("utf-8")) > 800:
        return False
    q = _compact(question)
    issuer = any(x in q for x in ("恒瑞医药", "600276", "hengrui"))
    period = (bool(re.search(r"2026.{0,6}(?:上半年|半年度|h1)", q))
              or "firsthalfof2026" in q)
    consolidated = "合并" in q or "consolidated" in q
    revenue = any(x in q for x in ("营业收入", "营收", "revenue"))
    return issuer and period and consolidated and revenue


def _withheld(reason: str) -> dict:
    return {
        "status": "WITHHELD",
        "reason": reason,
        "proposal": None,
        "financial_semantic_review": "NOT_PERFORMED",
        "research_publication": "BLOCKED",
    }


def _fits_single_revenue_lookup(candidate: CompactIntent) -> bool:
    """Structural routing gate, deliberately not a semantic certification."""
    if candidate.operation != QuestionOperation.LOOKUP:
        return False
    if candidate.numerator is not None or candidate.denominator is not None:
        return False
    if not candidate.metric or not candidate.reporting_scope:
        return False
    metric = _compact(candidate.metric)
    scope = _compact(candidate.reporting_scope)
    if any(term in metric for term in ("创新药", "药品销售", "母公司", "parent")):
        return False
    return (
        any(x in metric for x in ("营业收入", "营收", "revenue"))
        and ("合并" in scope or "consolidated" in scope)
    )


def propose(
    question: str,
    *,
    api_key: str,
    client: httpx.Client | None = None,
) -> dict:
    """At most one paid call. All outputs stay unpublished and unverified."""
    if not in_current_source_scope(question):
        return _withheld("QUESTION_OUTSIDE_SUPPORTED_SCOPE")
    if not api_key or not api_key.strip():
        return _withheld("MODEL_NOT_CONFIGURED")

    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": question},
        ],
        "thinking": {"type": "disabled"},
        "response_format": {"type": "json_object"},
        "temperature": 0,
        "max_tokens": 384,
        "stream": False,
    }
    own_client = client is None
    if own_client:
        proxy = os.environ.get("FRP_DEEPSEEK_PROXY") or None
        client = httpx.Client(
            proxy=proxy,
            trust_env=proxy is None,
            timeout=45,
            follow_redirects=False,
        )
    try:
        assert client is not None
        response = deepseek_draft._send(body, api_key, client)
    except deepseek_draft.ProviderFailure:
        return _withheld("MODEL_PROVIDER_UNAVAILABLE")
    finally:
        if own_client and client is not None:
            client.close()

    try:
        if response.get("model") != MODEL:
            return _withheld("MODEL_MISMATCH")
        choices = response["choices"]
        if (not isinstance(choices, list) or len(choices) != 1
            or choices[0]["finish_reason"] != "stop"):
            return _withheld("MODEL_RESPONSE_INCOMPLETE")
        content = choices[0]["message"]["content"]
        if (not isinstance(content, str)
            or len(content.encode("utf-8")) > 6000):
            return _withheld("MODEL_CONTENT_INVALID")
        candidate = CompactIntent.model_validate_json(content)
        if not _fits_single_revenue_lookup(candidate):
            return _withheld("MODEL_INTENT_OUTSIDE_SUPPORTED_SCOPE")
        proposal = QuestionIntentProposal(
            question=question,
            operation_candidate=candidate.operation,
            metric_candidate=candidate.metric,
            numerator_candidate=candidate.numerator,
            denominator_candidate=candidate.denominator,
            reporting_scope_candidate=candidate.reporting_scope,
            unresolved=tuple(candidate.unresolved),
        )
    except (KeyError, TypeError, ValueError, IndexError):
        return _withheld("MODEL_PROPOSAL_INVALID")

    # The source key is server-selected, never supplied by the model.
    # Notes in proposal.unresolved are untrusted (including temporal claims).
    return {
        "status": "INTENT_PROPOSAL_READY",
        "model": MODEL,
        "report_key": REPORT_KEY,
        "proposal": proposal.model_dump(mode="json"),
        "interpretation_status": "UNVERIFIED_PROPOSAL",
        "financial_semantic_review": "NOT_PERFORMED",
        "research_publication": "BLOCKED",
    }
