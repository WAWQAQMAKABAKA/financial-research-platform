"""M2a question route: dev-only access control and response shape."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

TOKEN = "m1-local-dev-token-0123456789abcdef"
PDF = Path(__file__).resolve().parents[3] / "data/raw/600760/2026H1/source.pdf"
URL = "/api/v1/research/reports/600760-2026H1/ask"
QUESTION = "中航沈飞2026年半年度合并利润表中营业收入是多少？"


def authorize(monkeypatch, pdf: str | None = "auto") -> None:
    monkeypatch.setenv("FRP_LOCAL_FACTS_REPORT", "1")
    monkeypatch.setenv("FRP_LOCAL_LLM_ACCESS_TOKEN", TOKEN)
    monkeypatch.delenv("FRP_ENV", raising=False)
    monkeypatch.setenv(
        "FRP_LOCAL_SOURCE_PDF_600760",
        str(PDF) if pdf == "auto" else (pdf or ""),
    )


def ask(url: str = URL, token: str | None = TOKEN, question: str = QUESTION, **extra):
    headers = {} if token is None else {"x-frp-local-token": token}
    body = {"question": question, **extra}
    return TestClient(app).post(url, json=body, headers=headers)


def test_route_is_off_by_default(monkeypatch):
    monkeypatch.delenv("FRP_LOCAL_FACTS_REPORT", raising=False)
    assert ask().status_code == 404


def test_missing_or_wrong_token_is_refused(monkeypatch):
    authorize(monkeypatch)
    assert ask(token=None).status_code == 404
    assert ask(token="wrong-token-but-long-enough-000000").status_code == 404


def test_production_environment_is_refused(monkeypatch):
    authorize(monkeypatch)
    monkeypatch.setenv("FRP_ENV", "production")
    assert ask().status_code == 404


def test_unknown_and_legacy_reports_are_refused(monkeypatch):
    authorize(monkeypatch)
    assert ask("/api/v1/research/reports/999999-2026H1/ask").status_code == 404
    assert ask("/api/v1/research/reports/600276-2026H1/ask").status_code == 404


def test_missing_pdf_path_is_unavailable(monkeypatch):
    authorize(monkeypatch, pdf="")
    response = ask()
    assert response.status_code == 503
    assert response.json() == {"detail": "SOURCE_UNAVAILABLE"}


@pytest.mark.parametrize("question", ["", "x", "x" * 241])
def test_invalid_question_length_is_rejected(monkeypatch, question):
    authorize(monkeypatch)
    assert ask(question=question).status_code == 422


def test_extra_fields_are_rejected(monkeypatch):
    authorize(monkeypatch)
    assert ask(unexpected="value").status_code == 422


def test_authorized_question_returns_verified_facts(monkeypatch):
    if not PDF.is_file():
        pytest.skip("authorized 600760 PDF not provisioned locally")
    authorize(monkeypatch)

    response = ask()
    assert response.status_code == 200
    report = response.json()
    assert report["status"] == "REPORT_READY"
    assert report["report_type"] == "FACTS_ONLY_QUESTION_REPORT"
    assert report["facts"][0]["value_verbatim"] == "6,191,107,217.36"
    assert report["publication"]["research_publication"] == "FACTS_ONLY"


ASK_URL = "/api/v1/research/reports/600760-2026H1/ask"
RESOLVE_URL = "/api/v1/research/reports/600760-2026H1/ask/resolve"
NET_PROFIT_QUESTION = "600760 中航沈飞 2026 年半年度合并利润表的净利是多少？"


def ask_net_profit():
    headers = {"x-frp-local-token": TOKEN}
    return TestClient(app).post(ASK_URL, json={"question": NET_PROFIT_QUESTION},
                                headers=headers)


def resolve(question, clarification_id, option_id):
    headers = {"x-frp-local-token": TOKEN}
    return TestClient(app).post(
        RESOLVE_URL,
        json={"question": question, "clarification_id": clarification_id,
              "option_id": option_id},
        headers=headers,
    )


def test_ambiguous_metric_returns_clarification(monkeypatch):
    if not PDF.is_file():
        pytest.skip("authorized 600760 PDF not provisioned locally")
    authorize(monkeypatch)
    monkeypatch.delenv("FRP_LOCAL_CLARIFY_LLM", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    response = ask_net_profit()
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "CLARIFICATION_REQUIRED"
    assert body["reason"] == "METRIC_IDENTITY_AMBIGUOUS"
    assert len(body["options"]) >= 2
    assert body["research_publication"] == "BLOCKED"
    assert body["clarification_id"]
    cores = {option["core"] for option in body["options"]}
    assert "归属于母公司股东的净利润" in cores
    assert "净利润" in cores


def test_clarification_resolve_roundtrip(monkeypatch):
    if not PDF.is_file():
        pytest.skip("authorized 600760 PDF not provisioned locally")
    authorize(monkeypatch)
    monkeypatch.delenv("FRP_LOCAL_CLARIFY_LLM", raising=False)

    clarification = ask_net_profit().json()
    attributable = next(
        option for option in clarification["options"]
        if option["core"] == "归属于母公司股东的净利润"
    )

    result = resolve(
        NET_PROFIT_QUESTION, clarification["clarification_id"],
        attributable["option_id"],
    )
    assert result.status_code == 200
    report = result.json()
    assert report["status"] == "REPORT_READY"
    assert len(report["facts"]) == 1
    assert report["facts"][0]["row_label"].startswith("1.归属于母公司股东的净利润")
    assert report["facts"][0]["value_verbatim"] == "473,065,863.24"
    assert report["selection"]["trace"]["selection_basis"] == "USER_RESOLVED_METRIC"


def test_resolve_rejects_tampered_token(monkeypatch):
    if not PDF.is_file():
        pytest.skip("authorized 600760 PDF not provisioned locally")
    authorize(monkeypatch)
    monkeypatch.delenv("FRP_LOCAL_CLARIFY_LLM", raising=False)

    clarification = ask_net_profit().json()
    option_id = clarification["options"][0]["option_id"]
    tampered = clarification["clarification_id"][:-1] + (
        "0" if clarification["clarification_id"][-1] != "0" else "1"
    )

    result = resolve(NET_PROFIT_QUESTION, tampered, option_id)
    assert result.status_code == 422


def test_resolve_rejects_unoffered_option(monkeypatch):
    if not PDF.is_file():
        pytest.skip("authorized 600760 PDF not provisioned locally")
    authorize(monkeypatch)
    monkeypatch.delenv("FRP_LOCAL_CLARIFY_LLM", raising=False)

    clarification = ask_net_profit().json()
    result = resolve(NET_PROFIT_QUESTION, clarification["clarification_id"], "f" * 64)
    assert result.status_code == 422


def test_scope_resolve_runs_the_chosen_statement(monkeypatch):
    if not PDF.is_file():
        pytest.skip("authorized 600760 PDF not provisioned locally")
    authorize(monkeypatch)
    from hashlib import sha256
    from app.evidence.corpus_manifest import load_corpus_manifest
    from app.modules.financial_report_analyst import clarification as cl

    document = load_corpus_manifest().require_report_key("600760-2026H1")
    secret = sha256(TOKEN.encode("utf-8")).hexdigest()
    ids = [
        cl.scope_option_id(document, "consolidated_income_statement"),
        cl.scope_option_id(document, "parent_income_statement"),
    ]
    token = cl.sign_clarification(
        question="营业收入是多少？", document=document, report_key="600760-2026H1",
        statement_kind=None, option_ids=ids, secret=secret, kind="STATEMENT_SCOPE",
    )

    result = resolve("营业收入是多少？", token, ids[0])
    assert result.status_code == 200
    report = result.json()
    assert report["status"] == "REPORT_READY"
    assert report["facts"][0]["value_verbatim"] == "6,191,107,217.36"
    assert report["selection"]["trace"]["selection_basis"] == "USER_RESOLVED_STATEMENT_SCOPE"


def test_dual_statement_question_is_still_rejected(monkeypatch):
    if not PDF.is_file():
        pytest.skip("authorized 600760 PDF not provisioned locally")
    authorize(monkeypatch)
    headers = {"x-frp-local-token": TOKEN}

    response = TestClient(app).post(
        ASK_URL,
        json={"question": "600760 中航沈飞 2026 年半年度合并利润表和母公司利润表的营业收入各是多少？"},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "REPORT_WITHHELD"
    assert body["reason"] == "AMBIGUOUS_STATEMENT_SCOPE"


def test_ask_offers_scope_choice_and_resolve_publishes(monkeypatch):
    if not PDF.is_file():
        pytest.skip("authorized 600760 PDF not provisioned locally")
    authorize(monkeypatch)
    headers = {"x-frp-local-token": TOKEN}

    asked = TestClient(app).post(
        ASK_URL, json={"question": "利润总额是多少？"}, headers=headers,
    )
    assert asked.status_code == 200
    clarification = asked.json()
    assert clarification["status"] == "CLARIFICATION_REQUIRED"
    assert clarification["kind"] == "STATEMENT_SCOPE"
    assert [o["statement_title"] for o in clarification["options"]] == [
        "合并利润表", "母公司利润表"
    ]
    consolidated = clarification["options"][0]

    resolved = resolve("利润总额是多少？", clarification["clarification_id"],
                       consolidated["option_id"])
    assert resolved.status_code == 200
    report = resolved.json()
    assert report["status"] == "REPORT_READY"
    assert report["facts"][0]["value_verbatim"] == "565,393,924.81"
    assert report["selection"]["trace"]["selection_basis"] == "USER_RESOLVED_STATEMENT_SCOPE"


def test_multi_fact_question_returns_coverage(monkeypatch):
    if not PDF.is_file():
        pytest.skip("authorized 600760 PDF not provisioned locally")
    authorize(monkeypatch)
    headers = {"x-frp-local-token": TOKEN}

    response = TestClient(app).post(
        ASK_URL,
        json={"question": "600760 中航沈飞 2026 年半年度合并利润表中营业收入和净利润分别是多少？"},
        headers=headers,
    )
    assert response.status_code == 200
    report = response.json()
    assert report["status"] == "REPORT_READY"
    assert report["report_type"] == "FACTS_ONLY_MULTI_REQUIREMENT_REPORT"
    assert len(report["facts"]) == 2
    assert report["coverage"]["complete"] is True
