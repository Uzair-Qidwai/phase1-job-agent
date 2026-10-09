import hashlib
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import pytest
from psycopg2.extras import Json

from src import digest_review as review, tracker, delivery
from src.settings import get_settings

pytestmark = pytest.mark.skipif(not os.getenv('POSTGRES_URL'), reason='POSTGRES_URL required')
SOURCE = '# Candidate\n\nBuilt evidence-based evaluation tools.'


def cleanup():
    with tracker.get_conn() as conn, conn.cursor() as cur:
        cur.execute('DELETE FROM digest_batches')
        cur.execute('DELETE FROM delivery_attempts')
        cur.execute('DELETE FROM notifications')
        cur.execute('DELETE FROM pipeline_events')
        cur.execute('DELETE FROM pipeline_runs')
        cur.execute("UPDATE jobs SET cv_version_id=NULL WHERE source='review-test'")
        cur.execute("DELETE FROM cv_versions WHERE job_id IN (SELECT id FROM jobs WHERE source='review-test')")
        cur.execute("DELETE FROM jobs WHERE source='review-test'")


@pytest.fixture(autouse=True)
def isolated_review(monkeypatch):
    monkeypatch.setenv('GMAIL_SENDER', 'sender@example.com')
    monkeypatch.setenv('DIGEST_RECIPIENT', 'recipient@example.com')
    monkeypatch.setenv('DIGEST_DELIVERY_MODE', 'review')
    get_settings.cache_clear()
    monkeypatch.setattr(review, '_load_master_cv', lambda: SOURCE)
    cleanup()
    yield
    cleanup()
    get_settings.cache_clear()


def make_job():
    job_id, _ = tracker.upsert_job('AI Engineer', 'Example', 'Toronto',
                                  f'https://example.com/jobs/{uuid4()}', 'Build evaluation tools.', 'review-test')
    cv = tracker.save_cv_version(job_id, SOURCE, 'UNVERIFIED MODEL COMMENTARY',
                                source_cv_sha256=hashlib.sha256(SOURCE.encode()).hexdigest(),
                                validation={'valid': True})
    tracker.attach_cv_version(job_id, cv)
    tracker.update_job_score(job_id, .9)
    tracker.update_job_system_state(job_id, 'tailored')
    return job_id


def prepared():
    return review.prepare_batch([make_job()])


def test_saved_content_requires_exact_approval_and_sends_once(monkeypatch):
    batch = prepared();bid = str(batch['id']);digest = batch['fingerprint'];sent = []
    assert batch['status'] == 'pending'
    assert 'UNVERIFIED MODEL COMMENTARY' not in batch['snapshot']['html']
    with pytest.raises(ValueError, match='not approved'):
        review.send_batch(bid, digest, transport=lambda *a, **k: pytest.fail('Unapproved send'))
    with pytest.raises(ValueError, match='fingerprint'):
        review.approve_batch(bid, '0'*64)
    review.approve_batch(bid, digest)
    monkeypatch.setattr(review, '_build_html', lambda *a, **k: pytest.fail('Must not rerender'))
    def send(snapshot, **kwargs):
        sent.append((snapshot, kwargs['message_id']))
        return True
    assert review.send_batch(bid, digest, transport=send) == 1
    assert sent[0][0] == batch['snapshot']
    assert review.get_batch(bid)['status'] == 'sent'
    with pytest.raises(ValueError, match='already sent'):
        review.send_batch(bid, digest, transport=send)
    assert len(sent) == 1
    assert not tracker.get_new_jobs_for_digest()


@pytest.mark.parametrize('change', ['job', 'description', 'cv', 'source', 'recipient', 'snapshot', 'notified'])
def test_changed_preview_cannot_send(change, monkeypatch):
    batch = prepared();bid = str(batch['id']);digest = batch['fingerprint']
    review.approve_batch(bid, digest)
    job = batch['snapshot']['jobs'][0]
    if change == 'source':
        monkeypatch.setattr(review, '_load_master_cv', lambda: SOURCE+' updated')
    elif change == 'recipient':
        monkeypatch.setenv('DIGEST_RECIPIENT', 'different@example.com');get_settings.cache_clear()
    else:
        with tracker.get_conn() as conn, conn.cursor() as cur:
            if change == 'job':
                cur.execute('UPDATE jobs SET title=%s WHERE id=%s', ('Changed role',job['id']))
            elif change == 'description':
                cur.execute('UPDATE jobs SET description=%s WHERE id=%s', ('Different requirements',job['id']))
            elif change == 'cv':
                cur.execute('UPDATE cv_versions SET tailored_cv=%s WHERE id=%s', ('Changed CV',job['cv_version_id']))
            elif change == 'snapshot':
                snap=batch['snapshot'];snap['html']='Different email'
                cur.execute('UPDATE digest_batches SET snapshot=%s WHERE id=%s',(Json(snap),bid))
            else:
                cur.execute("UPDATE jobs SET system_state='notified' WHERE id=%s",(job['id'],))
    with pytest.raises(ValueError):
        review.send_batch(bid,digest,transport=lambda *a,**k:pytest.fail('Stale preview sent'))
    assert not delivery.list_attempts()


def test_cancel_then_reprepare_requires_new_approval():
    first=prepared();review.approve_batch(str(first['id']),first['fingerprint'])
    review.cancel_batch(str(first['id']))
    with pytest.raises(ValueError):review.send_batch(str(first['id']),first['fingerprint'])
    second=review.prepare_batch()
    assert second['id'] != first['id'] and second['status']=='pending'
    assert second['approved_fingerprint'] is None


def test_repeated_prepare_returns_existing_batch_and_does_not_add_jobs():
    first=prepared();make_job()
    second=review.prepare_batch()
    assert first['id']==second['id'] and len(second['snapshot']['jobs'])==1
    assert len(review.list_batches())==1


def test_concurrent_send_has_one_transport_call():
    batch=prepared();bid=str(batch['id']);digest=batch['fingerprint']
    review.approve_batch(bid,digest);entered=Event();release=Event();calls=[]
    def send(snapshot,**kwargs):
        calls.append(snapshot);entered.set();assert release.wait(5);return True
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(review.send_batch,bid,digest,transport=send)
        try:
            assert entered.wait(5)
            with pytest.raises(tracker.PipelineAlreadyRunning):
                review.send_batch(bid,digest,transport=send)
        finally:release.set()
        assert first.result(timeout=5)==1
    assert len(calls)==1


@pytest.mark.parametrize('acknowledged', [False,True])
def test_crash_and_reconciliation_preserve_approval_boundary(monkeypatch,acknowledged):
    batch=prepared();bid=str(batch['id']);digest=batch['fingerprint']
    review.approve_batch(bid,digest);calls=[]
    def send(snapshot,**kwargs):
        if not acknowledged:raise RuntimeError('transport failed')
        calls.append(snapshot);return True
    original=delivery.finish_attempt
    if acknowledged:
        def crash(*a,**k):raise RuntimeError('crash after external send')
        monkeypatch.setattr(delivery,'finish_attempt',crash)
    with pytest.raises((RuntimeError,delivery.DeliveryAmbiguous)):
        review.send_batch(bid,digest,transport=send)
    assert review.get_batch(bid)['status']=='sending'
    with pytest.raises(ValueError):review.send_batch(bid,digest,transport=send)
    with pytest.raises(ValueError):review.cancel_batch(bid)
    monkeypatch.setattr(delivery,'finish_attempt',original)
    attempt=delivery.list_attempts()[0]
    delivery.reconcile(str(attempt['id']),sent=acknowledged,
                       reason='Verified external outcome in controlled test',workers_stopped=True)
    current=review.get_batch(bid)
    assert current['status']==('sent' if acknowledged else 'pending')
    if not acknowledged:
        assert current['approved_fingerprint'] is None
        with pytest.raises(ValueError):review.send_batch(bid,digest,transport=send)
        review.approve_batch(bid,digest)
        assert review.send_batch(bid,digest,transport=lambda *a,**k:True)==1
    assert len(calls)==int(acknowledged)


def test_default_pipeline_saves_preview_without_transport(monkeypatch):
    from src import scraper,cv_agent,emailer
    from src.scheduler import run_pipeline
    async def scrape(headless=True):
        return [scraper.RawJob('AI Engineer','Example','Toronto',f'https://example.com/{uuid4()}',
                              'AI machine learning Python evaluation','review-test')]
    def tailor(**kwargs):
        return {'tailored_cv':SOURCE,'changes_made':'Unverified commentary',
                'model':'fixture','prompt_version':'fixture','profile_version':'1',
                'source_cv_sha256':hashlib.sha256(SOURCE.encode()).hexdigest(),
                'evidence_used':[],'validation':{'valid':True}}
    monkeypatch.setattr(scraper,'scrape_all',scrape)
    monkeypatch.setattr(cv_agent,'tailor_cv',tailor)
    monkeypatch.setattr(emailer,'send_digest',lambda *a,**k:pytest.fail('Pipeline sent unapproved email'))
    run=tracker.get_pipeline_run(run_pipeline('manual'))
    assert run['status']=='completed' and run['jobs_tailored']==1 and run['jobs_notified']==0
    assert review.list_batches()[0]['status']=='pending'
    assert not delivery.list_attempts()


def test_automatic_delivery_cannot_bypass_open_review():
    batch=prepared()
    run=tracker.start_pipeline_run('manual')
    with pytest.raises(delivery.DeliveryAmbiguous,match='Open review'):
        delivery.deliver_digest(batch['snapshot']['jobs'],run_id=run,
                                send=lambda *a,**k:pytest.fail('Bypassed review'))
    assert not delivery.list_attempts()


def test_authenticated_api_review_and_send_flow(monkeypatch):
    from fastapi.testclient import TestClient
    from src.api import app
    monkeypatch.setenv('API_TOKEN','review-test-token-at-least-24-characters')
    get_settings.cache_clear()
    headers={'Authorization':'Bearer review-test-token-at-least-24-characters'}
    client=TestClient(app);sent=[]
    monkeypatch.setattr(review,'send_snapshot',lambda snapshot,**kwargs:sent.append(snapshot) or True)
    response=client.post('/digests',headers=headers,json={'job_ids':[make_job()]})
    assert response.status_code==200
    batch=response.json();path='/digests/'+batch['id'];body={'fingerprint':batch['fingerprint']}
    assert client.get(path,headers=headers).json()['snapshot']==batch['snapshot']
    assert client.post(path+'/send',headers=headers,json=body).status_code==409
    assert client.post(path+'/approve',headers=headers,json=body).status_code==200
    assert client.post(path+'/send',headers=headers,json=body).json()=={'jobs_notified':1}
    assert client.post(path+'/send',headers=headers,json=body).status_code==409
    assert sent==[batch['snapshot']]


def test_old_neutral_snapshot_remains_sendable_without_regeneration():
    batch=prepared();snapshot=batch['snapshot'];snapshot['version']=1
    for job in snapshot['jobs']:
        job.pop('observed_changes')
        job['changes_made']='CV preview available for review; qualifications require verification.'
    # Simulate a persisted version-one preview created before deterministic summaries.
    digest=review.fingerprint(snapshot)
    with tracker.get_conn() as conn,conn.cursor() as cur:
        cur.execute('UPDATE digest_batches SET snapshot=%s,fingerprint=%s WHERE id=%s',
                    (Json(snapshot),digest,batch['id']))
    review.approve_batch(str(batch['id']),digest)
    sent=[]
    assert review.send_batch(str(batch['id']),digest,
                             transport=lambda snapshot,**kw:sent.append(snapshot) or True)==1
    assert sent[0]==snapshot


def test_preview_uses_real_diff_instead_of_unverified_stored_summary():
    batch=prepared();job=batch['snapshot']['jobs'][0]
    assert batch['snapshot']['version']==2
    assert job['changes_made']=='Source CV unchanged.'
    assert job['observed_changes']['diff']==''
    assert 'UNVERIFIED MODEL COMMENTARY' not in batch['snapshot']['html']
