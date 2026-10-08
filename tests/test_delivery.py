import os
from uuid import uuid4

import pytest

from src import delivery
from src.tracker import get_conn, start_pipeline_run, upsert_job, pipeline_execution_lock, PipelineAlreadyRunning

pytestmark = pytest.mark.skipif(not os.getenv("POSTGRES_URL"), reason="POSTGRES_URL required")


@pytest.fixture
def batch():
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM delivery_attempts")
        cur.execute("DELETE FROM pipeline_events")
        cur.execute("DELETE FROM notifications")
        cur.execute("DELETE FROM pipeline_runs")
    job_id, _ = upsert_job("Engineer", "Example", "Toronto", f"https://example.com/{uuid4()}",
                          "Python systems", "delivery-test")
    run_id = start_pipeline_run("manual")
    yield [{"id": job_id}], run_id
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM delivery_attempts")
        cur.execute("DELETE FROM notifications")
        cur.execute("DELETE FROM pipeline_events")
        cur.execute("DELETE FROM pipeline_runs")
        cur.execute("DELETE FROM jobs WHERE source = 'delivery-test'")


@pytest.mark.parametrize("boundary", ["before_transport", "after_transport"])
def test_crash_never_automatically_resends(batch, monkeypatch, boundary):
    jobs, run_id = batch
    sent = []
    def send(jobs, **kwargs):
        sent.append(kwargs["message_id"])
        return True
    if boundary == "before_transport":
        delivery.prepare_attempt([jobs[0]["id"]], run_id)
    else:
        def crash(*args, **kwargs):
            raise RuntimeError("simulated database outage after external send")
        monkeypatch.setattr(delivery, "finish_attempt", crash)
        with pytest.raises(RuntimeError, match="database outage"):
            delivery.deliver_digest(jobs, run_id=run_id, send=send)
        monkeypatch.undo()
    with pytest.raises(delivery.DeliveryAmbiguous):
        delivery.deliver_digest(jobs, run_id=run_id, send=send)
    assert len(sent) == (boundary == "after_transport")
    attempt = delivery.list_attempts()[0]
    delivery.reconcile(str(attempt["id"]), sent=boundary == "after_transport",
                       reason="Verified transport result in controlled test", workers_stopped=True)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM notifications")
        assert cur.fetchone()["n"] == (boundary == "after_transport")
    if boundary == "before_transport":
        assert delivery.deliver_digest(jobs, run_id=run_id, send=send) == 1
    with pytest.raises(ValueError, match="already resolved"):
        delivery.reconcile(str(attempt["id"]), sent=False, reason="Another resolution attempt",
                           workers_stopped=True)


def test_reconciliation_requires_shutdown_and_excludes_worker(batch):
    jobs, run_id = batch
    attempt = delivery.prepare_attempt([jobs[0]["id"]], run_id)
    args = dict(sent=False, reason="Verified no external delivery occurred")
    with pytest.raises(ValueError, match="Stop workers"):
        delivery.reconcile(str(attempt["id"]), workers_stopped=False, **args)
    with pipeline_execution_lock(), pytest.raises(PipelineAlreadyRunning):
        delivery.reconcile(str(attempt["id"]), workers_stopped=True, **args)


def test_send_exception_is_sanitized_and_remains_ambiguous(batch):
    def send(*args, **kwargs):
        raise RuntimeError("secret-provider-payload")
    with pytest.raises(delivery.DeliveryAmbiguous) as error:
        delivery.deliver_digest(batch[0], run_id=batch[1], send=send)
    assert "secret-provider" not in str(error.value)
    assert delivery.list_attempts()[0]["status"] == "ambiguous"
