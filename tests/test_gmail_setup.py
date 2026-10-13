from types import SimpleNamespace

import pytest

from scripts import configure_gmail


def test_setup_saves_send_only_credentials_locally_without_printing(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(configure_gmail, '__file__', str(tmp_path / 'scripts' / 'configure_gmail.py'))
    monkeypatch.setattr(configure_gmail.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=0))
    monkeypatch.setattr('sys.argv', ['setup', '--client-file', str(tmp_path / 'client.json'),
                                   '--sender', 'sender@example.com', '--recipient', 'recipient@example.com'])
    calls = []
    class FakeFlow:
        def run_local_server(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(refresh_token='private-refresh', client_id='client-id', client_secret='private-client')
    def factory(path, scopes):
        assert scopes == ['https://www.googleapis.com/auth/gmail.send']
        return FakeFlow()
    monkeypatch.setattr(configure_gmail.InstalledAppFlow, 'from_client_secrets_file', factory)
    (tmp_path / '.env').write_text('EXISTING_SETTING=keep\n')
    configure_gmail.main()
    contents = (tmp_path / '.env').read_text()
    assert 'EXISTING_SETTING=keep' in contents
    assert 'private-refresh' in contents
    assert (tmp_path / '.env').stat().st_mode & 0o777 == 0o600
    assert 'private' not in capsys.readouterr().out
    assert calls[0]['host'] == 'localhost'


def test_setup_refuses_nonignored_secret_file_before_authorization(monkeypatch, tmp_path):
    monkeypatch.setattr(configure_gmail, '__file__', str(tmp_path / 'scripts' / 'configure_gmail.py'))
    monkeypatch.setattr(configure_gmail.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=1))
    monkeypatch.setattr('sys.argv', ['setup', '--client-file', 'unused', '--sender', 's@example.com', '--recipient', 'r@example.com'])
    monkeypatch.setattr(configure_gmail.InstalledAppFlow, 'from_client_secrets_file',
                        lambda *a, **kw: pytest.fail('Authorization must not start'))
    with pytest.raises(SystemExit):
        configure_gmail.main()
    assert not (tmp_path / '.env').exists()
