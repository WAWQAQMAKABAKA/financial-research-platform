"""M3: one bounded, opt-in DeepSeek interpretation for metric clarification.

The model proposes which *verified source rows* a question's metric phrase could
mean. It never selects source documents, never reads PDF text, never approves a
financial meaning, and never publishes. Its IDs are validated against the closed
server-selected option set before they are shown.

No API key or provider failure is fatal: the caller falls back to the
deterministic near-match option set and keeps the facts-only behavior.
"""
from __future__ import annotations

import os
import re

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.modules.financial_report_analyst import deepseek_draft

MODEL = "deepseek-flash"

SYSTEM = """
You interpret one Chinese financial-research question and propose which VERIFIED
source rows its metric could refer to.

Return ONLY valid JSON with exactly three fields:
operation, candidate_option_ids, rationale.

operation: the string "LOOKUP" when the question asks for a disclosed fact or
value. Otherwise use one of COMPARE, EXPLAIN, FORECAST, RATIO, VERIFY, UNKNOWN.

candidate_option_ids: a list of 2 to 4 option ids from the list provided below.
These are the rows this question's metric could plausibly mean. For an ambiguous
metric such as 净利, include BOTH 净利润 and 归属于母公司股东的净利润; do not
silently pick one. Use ONLY ids from the provided list. Never invent ids, labels,
values, or source documents.

rationale: one short Chinese sentence explaining why these rows are candidates
(and what is still ambiguous).

You must never produce a financial answer, a value, a comparison conclusion, or
investment advice.
"""


class CompactInterpretation(BaseModel):
    # The provider may echo response_format metadata (e.g. "type"); only the
    # three fields below are used, and option ids are still closed-set checked.
    model_config = ConfigDict(extra="ignore")

    operation: str = Field(min_length=1, max_length=24)
    candidate_option_ids: list[str]
    rationale: str = Field(min_length=1, max_length=400)


def _withheld(reason: str) -> dict:
    return {
        "status": "WITHHELD", "reason": reason,
        "operation": None, "candidate_option_ids": [],
        "rationale": None,
        "financial_semantic_review": "NOT_PERFORMED",
        "research_publication": "BLOCKED",
    }


def interpret(
    question: str,
    closed: list[dict],
    *,
    api_key: str,
    client: httpx.Client | None = None,
) -> dict:
    """At most one paid call. Outputs stay unpublished and unverified."""
    if not isinstance(question, str) or not (2 <= len(question) <= 240):
        return _withheld("QUESTION_INVALID")
    if not api_key or not api_key.strip():
        return _withheld("MODEL_NOT_CONFIGURED")

    option_lines = "\n".join(
        f"{option['option_id']} | {option['statement_title']} | "
        f"{option['core']} | {option['row_label']}"
        for option in closed
    )
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {
                "role": "user",
                "content": (
                    "Options (id | statement | core | verbatim label):\n"
                    f"{option_lines}\n\nQuestion:\n{question}"
                ),
            },
        ],
        "thinking": {"type": "disabled"},
        "response_format": {"type": "json_object"},
        "temperature": 0,
        "max_tokens": 512,
        "stream": False,
    }
    own_client = client is None
    if own_client:
        proxy = os.environ.get("FRP_DEEPSEEK_PROXY") or None
        client = httpx.Client(
            proxy=proxy, trust_env=proxy is None,
            timeout=45, follow_redirects=False,
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
                or choices[0].get("finish_reason") != "stop"):
            return _withheld("MODEL_RESPONSE_INCOMPLETE")
        content = choices[0]["message"]["content"]
        if not isinstance(content, str) or len(content.encode("utf-8")) > 6000:
            return _withheld("MODEL_CONTENT_INVALID")
        candidate = CompactInterpretation.model_validate_json(content)
    except (KeyError, TypeError, ValueError, IndexError):
        return _withheld("MODEL_PROPOSAL_INVALID")

    valid_ids = {option["option_id"] for option in closed}
    proposed = candidate.candidate_option_ids
    if (not isinstance(proposed, list)
            or any(not isinstance(i, str) for i in proposed)
            or any(i not in valid_ids for i in proposed)):
        return _withheld("MODEL_OPTIONS_OUTSIDE_CLOSED_SET")

    if not (2 <= len(proposed) <= 4):
        return _withheld("MODEL_OPTION_COUNT_INVALID")

    return {
        "status": "INTERPRETATION_READY",
        "model": MODEL,
        "operation": candidate.operation,
        "candidate_option_ids": proposed,
        "rationale": candidate.rationale,
        "interpretation_status": "UNVERIFIED_PROPOSAL",
        "financial_semantic_review": "NOT_PERFORMED",
        "research_publication": "BLOCKED",
    }


FACETS_SYSTEM = """
You split one Chinese financial-research question into independent disclosure-fact
requirements. Return ONLY valid JSON with exactly two fields: facets, rationale.

facets: 2 to 3 short Chinese noun phrases. Each names ONE metric the question asks
for, in the source's own vocabulary where possible. Do not include comparisons,
forecasts, causes, explanations, opinions, or values.

rationale: one short Chinese sentence describing the split.

Never answer the question, never provide numbers, never mention source pages.
"""


class FacetProposal(BaseModel):
    model_config = ConfigDict(extra="ignore")

    facets: list[str]
    rationale: str = Field(min_length=1, max_length=400)


def propose_facets(question: str, *, api_key: str,
                   client: httpx.Client | None = None) -> dict:
    """At most one paid call; facets still resolve through the verified index."""
    if not isinstance(question, str) or not (2 <= len(question) <= 240):
        return {"status": "WITHHELD", "reason": "QUESTION_INVALID",
                "facets": [], "rationale": None}
    if not api_key or not api_key.strip():
        return {"status": "WITHHELD", "reason": "MODEL_NOT_CONFIGURED",
                "facets": [], "rationale": None}

    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": FACETS_SYSTEM},
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
        client = httpx.Client(proxy=proxy, trust_env=proxy is None,
                              timeout=45, follow_redirects=False)
    try:
        assert client is not None
        response = deepseek_draft._send(body, api_key, client)
    except deepseek_draft.ProviderFailure:
        return {"status": "WITHHELD", "reason": "MODEL_PROVIDER_UNAVAILABLE",
                "facets": [], "rationale": None}
    finally:
        if own_client and client is not None:
            client.close()

    try:
        if response.get("model") != MODEL:
            return {"status": "WITHHELD", "reason": "MODEL_MISMATCH",
                    "facets": [], "rationale": None}
        choices = response["choices"]
        if (not isinstance(choices, list) or len(choices) != 1
                or choices[0].get("finish_reason") != "stop"):
            return {"status": "WITHHELD", "reason": "MODEL_RESPONSE_INCOMPLETE",
                    "facets": [], "rationale": None}
        content = choices[0]["message"]["content"]
        if not isinstance(content, str) or len(content.encode("utf-8")) > 6000:
            return {"status": "WITHHELD", "reason": "MODEL_CONTENT_INVALID",
                    "facets": [], "rationale": None}
        candidate = FacetProposal.model_validate_json(content)
    except (KeyError, TypeError, ValueError, IndexError):
        return {"status": "WITHHELD", "reason": "MODEL_PROPOSAL_INVALID",
                "facets": [], "rationale": None}

    facets = [facet.strip() for facet in candidate.facets
              if isinstance(facet, str) and 2 <= len(facet.strip()) <= 120]
    if (not 2 <= len(facets) <= 12
            or len({facet for facet in facets}) != len(facets)):
        return {"status": "WITHHELD", "reason": "MODEL_FACETS_INVALID",
                "facets": [], "rationale": None}

    return {
        "status": "FACETS_READY",
        "model": MODEL,
        "facets": facets,
        "rationale": candidate.rationale,
        "interpretation_status": "UNVERIFIED_PROPOSAL",
        "research_publication": "BLOCKED",
    }
