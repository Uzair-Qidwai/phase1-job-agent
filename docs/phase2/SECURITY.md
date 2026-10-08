# Phase 2 Security Contract

## Trust Model

The application is a private single-user system in Phase 2, but network exposure must be treated as possible.

Untrusted inputs include:

- scraped job titles, descriptions, companies, locations, and URLs;
- external HTTP responses;
- LLM-generated text and structured data;
- API request bodies and path parameters.

## Required Controls

### API

All mutation endpoints require authentication.

Protected operations include:

- pipeline execution;
- application-state changes;
- notes;
- manual re-ranking;
- manual CV generation;
- notification resend actions.

Identifiers are validated at the FastAPI boundary using typed UUID parameters.

### Pipeline Execution

Only one active run is allowed.

Manual and scheduled triggers must compete for the same lock.

Trigger endpoints must not directly create unlimited detached subprocesses.

### HTML and Links

All untrusted text is escaped before HTML rendering.

Links must use explicitly allowed schemes such as `https` and `http`.

Do not interpolate arbitrary scraped or generated values directly into executable HTML/JavaScript contexts.

### Secrets

Secrets are read through a validated configuration layer and are never committed.

Required ignore rules include at least:

- .env
- OAuth credential/token files
- virtual environments
- caches
- local database artifacts

Application logs must not print access tokens, API keys, refresh tokens, or connection strings.

### LLM Boundary

Job descriptions are data, not trusted instructions.

Generated outputs must pass typed schema validation.

A generated CV must pass the evidence gate before it is considered valid.

### Database

Database constraints enforce invariants independently of API validation.

At minimum:

- ranking scores remain in allowed ranges;
- state columns use constrained values;
- source identity is unique;
- notification records support idempotent delivery.

## Security Eval Requirements

CI tests must include:

- anonymous mutation rejected;
- anonymous pipeline trigger rejected;
- malformed UUID returns 4xx;
- script/HTML content is escaped in dashboard and digest;
- unsafe URL scheme is rejected;
- concurrent pipeline trigger is refused;
- secrets are absent from serialized API responses.
