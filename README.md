# Phase 1 — Job Search & CV Agent

Scrapes LinkedIn, Indeed, and Greenhouse daily → tailors your CV per listing via Claude API → tracks applications in PostgreSQL → sends HTML email digest → serves a live dashboard.

---

## Stack

| Component | Tool |
|-----------|------|
| CV tailoring | Claude API (`claude-sonnet-4-5`) |
| Job scraping | Playwright + BeautifulSoup + httpx |
| Database | PostgreSQL |
| Scheduling | APScheduler |
| Email digest | Gmail API (OAuth2) |
| Dashboard | FastAPI + HTML |

---

## Setup

### 1. Clone & install

```bash
git clone <your-repo>
cd phase1-job-agent

# Create venv and install (uv recommended)
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# Install Playwright browser
playwright install chromium
```

### 2. Configure environment

```bash
cp .env.example .env
# Fill in ANTHROPIC_API_KEY, POSTGRES_URL, Gmail credentials
```

### 3. Create the database

```bash
psql $POSTGRES_URL -f migrations/001_jobs.sql
```

### 4. Gmail OAuth setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project → enable Gmail API
3. Create OAuth credentials (Desktop app)
4. Run once to get tokens:

```python
from google_auth_oauthlib.flow import InstalledAppFlow
flow = InstalledAppFlow.from_client_secrets_file(
    "credentials.json", scopes=["https://www.googleapis.com/auth/gmail.send"]
)
creds = flow.run_local_server(port=0)
print("REFRESH_TOKEN:", creds.refresh_token)
```

5. Paste the refresh token into `.env`

### 5. Update master CV

Edit `data/master_cv.md` with your actual experience before running.

---

## Running

### Start dashboard + API

```bash
uvicorn src.api:app --reload --port 8000
# → http://localhost:8000/dashboard
```

### Run full pipeline once (manual trigger)

```bash
python -m src.scheduler --run-now
```

### Start daily scheduler (8 AM Toronto time)

```bash
python -m src.scheduler
```

### Run tests

```bash
pytest tests/ -v
```

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/jobs` | List jobs (`?status=new&min_score=0.6`) |
| `GET` | `/jobs/{id}` | Job detail + tailored CV |
| `PATCH` | `/jobs/{id}/status` | Update status `{"status":"applied"}` |
| `PATCH` | `/jobs/{id}/notes` | Add notes `{"notes":"..."}` |
| `GET` | `/dashboard` | HTML dashboard |
| `POST` | `/pipeline/run` | Trigger pipeline now |

---

## Validation Checklist

- [ ] Scraper returns 10+ jobs on first run without errors
- [ ] CV tailor produces meaningfully different output per job description
- [ ] No duplicate jobs inserted on second run
- [ ] Daily digest email arrives with correct jobs
- [ ] Dashboard shows all jobs, status updates persist
- [ ] Scheduler runs without manual intervention
