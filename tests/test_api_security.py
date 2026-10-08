from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import src.api as api_module
from src.settings import get_settings


def _auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer phase2-test-secret-token-strong-enough"}


@pytest.fixture(autouse=True)
def configured_api_token(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "phase2-test-secret-token-strong-enough")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_write_endpoint_requires_bearer_token() -> None:
    client = TestClient(api_module.app)
    response = client.patch(
        f"/jobs/{uuid4()}/status",
        json={"status": "applied"},
    )
    assert response.status_code == 401


def test_pipeline_trigger_requires_bearer_token() -> None:
    client = TestClient(api_module.app)
    response = client.post("/pipeline/run")
    assert response.status_code == 401


def test_missing_api_token_disables_writes(monkeypatch) -> None:
    monkeypatch.delenv("API_TOKEN", raising=False)
    get_settings.cache_clear()
    client = TestClient(api_module.app)

    response = client.post("/pipeline/run")
    assert response.status_code == 503


def test_malformed_uuid_is_422_before_database_access() -> None:
    client = TestClient(api_module.app)
    response = client.get("/jobs/not-a-uuid")
    assert response.status_code == 422


def test_dashboard_escapes_scraped_and_generated_content(monkeypatch) -> None:
    job_id = uuid4()

    def fake_jobs(**kwargs):
        return [
            {
                "id": job_id,
                "title": "<script>alert(1)</script>",
                "company": "<b>Bad Corp</b>",
                "location": "Toronto",
                "url": "javascript:alert(1)",
                "match_score": 0.91,
                "source": "<img src=x onerror=alert(1)>",
                "status": "new",
                "changes_made": "<svg onload=alert(1)>",
            }
        ]

    monkeypatch.setattr(api_module, "get_jobs", fake_jobs)
    client = TestClient(api_module.app)
    response = client.get("/dashboard")

    assert response.status_code == 200
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text
    assert 'href="#"' in response.text
    assert "javascript:alert(1)" not in response.text


def test_security_headers_are_present(monkeypatch) -> None:
    monkeypatch.setattr(api_module, "get_jobs", lambda **kwargs: [])
    client = TestClient(api_module.app)
    response = client.get("/dashboard")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_retry_endpoint_requires_bearer_token() -> None:
    client = TestClient(api_module.app)
    response = client.post(f"/pipeline/runs/{uuid4()}/retry")
    assert response.status_code == 401


def test_retry_endpoint_rejects_nonfailed_run(monkeypatch) -> None:
    run_id = uuid4()
    monkeypatch.setattr(api_module, "get_active_pipeline_run", lambda: None)
    monkeypatch.setattr(
        api_module,
        "get_pipeline_run",
        lambda value: {
            "id": run_id,
            "status": "completed",
            "current_stage": "completed",
        },
    )

    client = TestClient(api_module.app)
    response = client.post(
        f"/pipeline/runs/{run_id}/retry",
        headers=_auth_headers(),
    )

    assert response.status_code == 409


def test_retry_endpoint_launches_failed_run_recovery(monkeypatch) -> None:
    run_id = uuid4()
    launched = {}
    admitted_id = str(uuid4())
    monkeypatch.setattr(api_module, "start_pipeline_run", lambda *a, **kw: admitted_id)

    monkeypatch.setattr(api_module, "get_active_pipeline_run", lambda: None)
    monkeypatch.setattr(
        api_module,
        "get_pipeline_run",
        lambda value: {
            "id": run_id,
            "status": "failed",
            "current_stage": "notifying",
        },
    )

    def fake_popen(args, **kwargs):
        launched["args"] = args
        launched["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(api_module.subprocess, "Popen", fake_popen)

    client = TestClient(api_module.app)
    response = client.post(
        f"/pipeline/runs/{run_id}/retry",
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["retry_of_run_id"] == str(run_id)
    assert body["failed_stage"] == "notifying"
    assert launched["args"][-2:] == ["--admitted-run", admitted_id]
    assert body["run_id"] == admitted_id
