"""Load mounted credentials without storing them in image layers or command args."""
import os
import sys
from pathlib import Path
from urllib.parse import quote

from dotenv import dotenv_values


def runtime_environment(secret_dir=Path('/run/secrets')):
    environment = dict(os.environ)
    values = dotenv_values(secret_dir / 'app_env', interpolate=False)
    environment.update({key: value for key, value in values.items() if value is not None})
    password = (secret_dir / 'db_password').read_text().strip()
    if not password:
        raise ValueError('Database password is empty')
    environment.update(
        POSTGRES_URL=f'postgresql://job_agent:{quote(password, safe="")}@db:5432/job_agent',
        API_REQUIRE_READ_AUTH='true', DIGEST_DELIVERY_MODE='review',
        MASTER_CV_PATH='/run/secrets/master_cv',
    )
    if not environment.get('API_TOKEN'):
        raise ValueError('API_TOKEN must be configured')
    return environment


def main():
    try:
        environment = runtime_environment()
        command = sys.argv[1:]
        if not command:
            raise ValueError('Command is required')
        if command == ['python', '-m', 'src.scheduler'] and environment.get('ENABLE_SCHEDULER') != 'true':
            raise ValueError('Scheduler disabled: set ENABLE_SCHEDULER=true only after release approval')
    except (OSError, ValueError) as exc:
        # Avoid printing config values or credential-bearing exception details.
        print(f'Deployment startup refused ({type(exc).__name__}); check mounted configuration.', file=sys.stderr)
        return 1
    os.execvpe(command[0], command, environment)


if __name__ == '__main__':
    raise SystemExit(main())
