from pathlib import Path
import importlib.util

import pytest

spec = importlib.util.spec_from_file_location('deployment_entrypoint', Path(__file__).parents[1] / 'deploy/entrypoint.py')
entrypoint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entrypoint)


def test_deployment_forces_review_auth_and_private_paths(tmp_path):
    (tmp_path / 'app_env').write_text('API_TOKEN=example\nDIGEST_DELIVERY_MODE=automatic\nAPI_REQUIRE_READ_AUTH=false\nMASTER_CV_PATH=/unsafe\nGEMINI_API_KEY=literal${VALUE}\n')
    (tmp_path / 'db_password').write_text('special@:/password\n')
    env = entrypoint.runtime_environment(tmp_path)
    assert env['DIGEST_DELIVERY_MODE'] == 'review'
    assert env['API_REQUIRE_READ_AUTH'] == 'true'
    assert env['MASTER_CV_PATH'] == '/run/secrets/master_cv'
    assert 'special%40%3A%2Fpassword' in env['POSTGRES_URL']
    assert env['GEMINI_API_KEY'] == 'literal${VALUE}'


def test_missing_token_refuses_startup(tmp_path, monkeypatch):
    monkeypatch.delenv('API_TOKEN', raising=False)
    (tmp_path / 'app_env').write_text('')
    (tmp_path / 'db_password').write_text('password')
    with pytest.raises(ValueError):
        entrypoint.runtime_environment(tmp_path)
