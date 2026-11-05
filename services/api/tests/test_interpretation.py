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


def test_provider_echoed_metadata_is_ignored(monkeypatch):
    payload = {
        "type": "json_object",
        "operation": "LOOKUP",
        "candidate_option_ids": ["a" * 64, "b" * 64],
        "rationale": "净利可指净利润或归母净利润。",
    }
    monkeypatch.setattr(
        deepseek_draft, "_send",
        lambda body, api_key, client: response(payload),
    )

    result = interp.interpret("净利是多少？", CLOSED, api_key="key")

    assert result["status"] == "INTERPRETATION_READY"
    assert result["candidate_option_ids"] == ["a" * 64, "b" * 64]


def facet_response(payload):
    return {
        "model": interp.MODEL,
        "choices": [{"finish_reason": "stop", "message": {
            "content": json.dumps(payload, ensure_ascii=False),
        }}],
    }


def test_propose_facets_returns_valid_split(monkeypatch):
    monkeypatch.setattr(
        deepseek_draft, "_send",
        lambda body, api_key, client: facet_response({
            "facets": ["营业收入", "净利润"], "rationale": "两个独立指标。",
        }),
    )
    result = interp.propose_facets("营业收入和净利润分别是多少？", api_key="key")

    assert result["status"] == "FACETS_READY"
    assert result["facets"] == ["营业收入", "净利润"]


def test_propose_facets_rejects_a_single_facet(monkeypatch):
    monkeypatch.setattr(
        deepseek_draft, "_send",
        lambda body, api_key, client: facet_response({
            "facets": ["营业收入"], "rationale": "x",
        }),
    )
    result = interp.propose_facets("营业收入是多少？", api_key="key")

    assert result["reason"] == "MODEL_FACETS_INVALID"


def test_propose_facets_needs_a_key():
    result = interp.propose_facets("营业收入和净利润分别是多少？", api_key="")
    assert result["reason"] == "MODEL_NOT_CONFIGURED"


def test_propose_facets_accepts_four(monkeypatch):
    monkeypatch.setattr(
        deepseek_draft, "_send",
        lambda body, api_key, client: facet_response({
            "facets": ["营业收入", "净利润", "营业成本", "研发费用"],
            "rationale": "四个指标。",
        }),
    )
    result = interp.propose_facets("四个指标分别是多少？", api_key="key")

    assert result["status"] == "FACETS_READY"
    assert len(result["facets"]) == 4
