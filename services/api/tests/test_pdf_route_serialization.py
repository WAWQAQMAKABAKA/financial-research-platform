"""M1.7A: network-free single-process PDF route-serialization regression.

Synthetic endpoints only. No PDF files, model calls, or financial answers.
"""
from concurrent.futures import ThreadPoolExecutor
from inspect import signature
from threading import Event, Lock

from fastapi.testclient import TestClient

from app import main
from app.modules.financial_report_analyst import source_workspace


def test_all_pdf_routes_share_the_guard_and_keep_fastapi_signatures():
    paths = (
        "/api/v1/research/evidence-preview/{document_id}",
        "/api/v1/research/ask",
        "/api/v1/research/revenue-scope-preview",
        "/api/v1/research/source-workspace/{report_key}",
    )
    for path in paths:
        routes = [route for route in main.app.routes if getattr(route, "path", None) == path]
        assert len(routes) == 1
        endpoint = routes[0].endpoint
        assert endpoint.__wrapped__ is not None
        assert endpoint.__name__ == endpoint.__wrapped__.__name__
        assert signature(endpoint) == signature(endpoint.__wrapped__)


def test_workspace_request_holds_pdf_lock(monkeypatch):
    monkeypatch.setenv("FRP_LOCAL_SOURCE_WORKSPACE", "1")
    monkeypatch.setenv("FRP_LOCAL_SOURCE_PDF_600276", "/synthetic/test.pdf")
    observed = []

    def fake_build(*args, **kwargs):
        observed.append(main._PDF_REQUEST_LOCK.locked())
        return {"status": "WITHHELD", "research_publication": "BLOCKED",
                "financial_semantic_review": "NOT_PERFORMED", "observations": [],
                "claims": [], "reviews": []}

    monkeypatch.setattr(source_workspace, "build_source_workspace", fake_build)
    response = TestClient(main.app).get("/api/v1/research/source-workspace/600276-2026H1")
    assert response.status_code == 200
    assert observed == [True]
    assert main._PDF_REQUEST_LOCK.locked() is False


def test_pdf_routes_are_mutually_exclusive_under_parallel_requests(monkeypatch):
    monkeypatch.setenv("FRP_LOCAL_SOURCE_WORKSPACE", "1")
    monkeypatch.setenv("FRP_LOCAL_SOURCE_PDF_600276", "/synthetic/test.pdf")
    monkeypatch.setenv("FRP_LOCAL_SOURCE_PDF_600760", "/synthetic/test2.pdf")
    entered = Event()
    release = Event()
    tracking_lock = Lock()
    active = 0
    peak_active = 0
    count = 0

    def fake_build(*args, **kwargs):
        nonlocal active, peak_active, count
        with tracking_lock:
            active += 1
            count += 1
            peak_active = max(peak_active, active)
        entered.set()
        assert release.wait(timeout=8), "STOP: SYNTHETIC_REQUEST_NOT_RELEASED"
        with tracking_lock:
            active -= 1
        return {"status": "WITHHELD", "research_publication": "BLOCKED",
                "financial_semantic_review": "NOT_PERFORMED", "observations": [],
                "claims": [], "reviews": []}

    monkeypatch.setattr(source_workspace, "build_source_workspace", fake_build)
    second_started = Event()
    def request(key):
        if key == "600760-2026H1":
            second_started.set()
        return TestClient(main.app).get(f"/api/v1/research/source-workspace/{key}")

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(request, "600276-2026H1")
        assert entered.wait(timeout=5)
        second = pool.submit(request, "600760-2026H1")
        assert second_started.wait(timeout=5)
        # Holding the first worker forces overlap pressure; the request guard
        # must exclude a second PDF invocation until the first releases.
        try:
            assert not first.done()
            assert not second.done()
        finally:
            release.set()
        assert first.result(timeout=10).status_code == 200
        assert second.result(timeout=10).status_code == 200
    assert peak_active == 1
    assert active == 0
    assert count == 2
    assert main._PDF_REQUEST_LOCK.locked() is False


def test_pdf_guard_is_released_on_handler_exception(monkeypatch):
    monkeypatch.setenv("FRP_LOCAL_SOURCE_WORKSPACE", "1")
    monkeypatch.setenv("FRP_LOCAL_SOURCE_PDF_600276", "/synthetic/test.pdf")

    def fail(*args, **kwargs):
        assert main._PDF_REQUEST_LOCK.locked()
        raise ValueError("synthetic source error")

    monkeypatch.setattr(source_workspace, "build_source_workspace", fail)
    response = TestClient(main.app).get("/api/v1/research/source-workspace/600276-2026H1")
    assert response.status_code == 503
    assert response.json() == {"detail": "SOURCE_UNAVAILABLE"}
    assert main._PDF_REQUEST_LOCK.locked() is False


def test_request_fails_closed_if_pdf_guard_cannot_be_acquired(monkeypatch):
    monkeypatch.setenv("FRP_LOCAL_SOURCE_WORKSPACE", "1")
    monkeypatch.setenv("FRP_LOCAL_SOURCE_PDF_600276", "/synthetic/test.pdf")

    class AlwaysBusy:
        def acquire(self, *, timeout):
            assert 0 < timeout <= 120
            return False
        def release(self):
            raise AssertionError("never acquired")

    monkeypatch.setattr(main, "_PDF_REQUEST_LOCK", AlwaysBusy())
    response = TestClient(main.app).get("/api/v1/research/source-workspace/600276-2026H1")
    assert response.status_code == 503
    assert response.json() == {"detail": "SOURCE_UNAVAILABLE"}


def test_health_does_not_wait_for_pdf_lock(monkeypatch):
    class AlwaysBusy:
        def acquire(self, *, timeout):
            return False
        def release(self):
            raise AssertionError("health should never acquire PDF lock")
    monkeypatch.setattr(main, "_PDF_REQUEST_LOCK", AlwaysBusy())
    response = TestClient(main.app).get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
