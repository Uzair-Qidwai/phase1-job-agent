from src.emailer import _build_html


def test_digest_escapes_untrusted_job_content() -> None:
    html = _build_html(
        [
            {
                "title": "<script>alert(1)</script>",
                "company": "<b>Bad Corp</b>",
                "location": "Toronto",
                "url": "javascript:alert(1)",
                "match_score": 0.9,
                "changes_made": "<svg onload=alert(1)>",
                "source": "<img src=x onerror=alert(1)>",
            }
        ]
    )

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert 'href="#"' in html
    assert "javascript:alert(1)" not in html


def test_saved_email_is_transmitted_verbatim_without_attachments(monkeypatch):
    import base64
    from email import message_from_bytes
    from src import emailer
    class Settings:
        def require_gmail_credentials(self):
            return ('client','secret','refresh','sender@example.com','recipient@example.com')
    monkeypatch.setattr(emailer,'get_settings',lambda:Settings())
    sent=[]
    class Service:
        def users(self):return self
        def messages(self):return self
        def send(self,**kwargs):sent.append(kwargs);return self
        def execute(self):return {'id':'ack'}
    monkeypatch.setattr(emailer,'_get_gmail_service',lambda:Service())
    snapshot={'sender':'sender@example.com','recipient':'recipient@example.com',
              'subject':'Reviewed subject','html':'<p>Exact reviewed content</p>'}
    assert emailer.send_snapshot(snapshot,message_id='<test@example.com>')
    message=message_from_bytes(base64.urlsafe_b64decode(sent[0]['body']['raw']))
    assert message['To']==snapshot['recipient'] and message['Subject']==snapshot['subject']
    parts=message.get_payload()
    assert len(parts)==1 and parts[0].get_content_type()=='text/html'
    assert parts[0].get_payload(decode=True).decode()==snapshot['html']
    assert parts[0].get_content_disposition() is None
