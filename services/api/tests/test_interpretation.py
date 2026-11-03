"""M3 interpretation: one JSON proposal, validated against a closed option set."""
import json

import pytest

from app.modules.financial_report_analyst import deepseek_draft, interpretation as interp

CLOSED = [
    {"option_id": "a" * 64, "row_label": "五、净利润", "core": "净利润",
     "statement_title": "合并利润表", "statement_kind": "consolidated_income_statement"},
    {"option_id": "b" * 64, "row_label": "1.归属于母公司股东的净利润", "core": "归属于母公司股东的净利润",
     "statement_title": "合并利润表", "statement_kind": "consolidated_income_statement"},
]


def response(content: dict) -> dict:
    return {
        "model": interp.MODEL,
        "choices": [{"finish_reason": "stop", "message": {
            "content": json.dumps(content, ensure_ascii=False),
        }}],
    }


def test_interpret_returns_validated_candidates(monkeypatch):
    monkeypatch.setattr(
        deepseek_draft, "_send",
        lambda body, api_key, client: response({
            "operation": "LOOKUP",
            "candidate_option_ids": ["a" * 64, "b" * 64],
            "rationale": "净利可指净利润或归母净利润。",
        }),
    )

    result = interp.interpret("公司上半年的净利是多少？", CLOSED, api_key="key")

    assert result["status"] == "INTERPRETATION_READY"
    assert result["candidate_option_ids"] == ["a" * 64, "b" * 64]
    assert result["interpretation_status"] == "UNVERIFIED_PROPOSAL"


def test_interpret_rejects_ids_outside_closed_set(monkeypatch):
    monkeypatch.setattr(
        deepseek_draft, "_send",
        lambda body, api_key, client: response({
            "operation": "LOOKUP",
            "candidate_option_ids": ["a" * 64, "z" * 64],
            "rationale": "x",
        }),
    )

    result = interp.interpret("净利是多少？", CLOSED, api_key="key")

    assert result["status"] == "WITHHELD"
    assert result["reason"] == "MODEL_OPTIONS_OUTSIDE_CLOSED_SET"


def test_interpret_requires_two_to_four_options(monkeypatch):
    monkeypatch.setattr(
        deepseek_draft, "_send",
        lambda body, api_key, client: response({
            "operation": "LOOKUP", "candidate_option_ids": ["a" * 64], "rationale": "x",
        }),
    )

    result = interp.interpret("净利是多少？", CLOSED, api_key="key")

    assert result["reason"] == "MODEL_OPTION_COUNT_INVALID"


def test_interpret_without_key_is_withheld(monkeypatch):
    result = interp.interpret("净利是多少？", CLOSED, api_key="")

    assert result["status"] == "WITHHELD"
    assert result["reason"] == "MODEL_NOT_CONFIGURED"


def test_interpret_surfaces_provider_failure(monkeypatch):
    def fail(body, api_key, client):
        raise deepseek_draft.ProviderFailure("NETWORK_OR_TIMEOUT")

    monkeypatch.setattr(deepseek_draft, "_send", fail)

    result = interp.interpret("净利是多少？", CLOSED, api_key="key")

    assert result["reason"] == "MODEL_PROVIDER_UNAVAILABLE"
