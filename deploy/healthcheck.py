"""Check protected HTTP and its database dependency without printing secrets."""
import urllib.request
from dotenv import dotenv_values

values = dotenv_values('/run/secrets/app_env', interpolate=False)
request = urllib.request.Request('http://127.0.0.1:8000/pipeline/runs?limit=1',
                                 headers={'Authorization': 'Bearer ' + values['API_TOKEN']})
try:
    with urllib.request.urlopen(request, timeout=5) as response:
        assert response.status == 200
except Exception:
    raise SystemExit(1)
