# Reno AURA Guardian

Independent application health monitor and Tamil voice assistant. This repository
contains only Guardian; the ERP backend and frontend are hosted separately.

## Deploy on Render

Create a Blueprint from this repository to use `render.yaml`. The blueprint selects
a paid Starter web service and a 1 GB persistent disk. Review Render pricing before
creating the service. Publishing this repository does not deploy or purchase hosting.

Alternatively create a Python Web Service with the root directory left blank:

- Build: `pip install -r reno_guardian/requirements.txt`
- Start: `uvicorn reno_guardian.app:app --host 0.0.0.0 --port $PORT --workers 1 --no-access-log`
- Python: 3.11 or newer (blueprint pins 3.13.5).
- Health check: `/health`.
- Use one instance and one worker. The current voice capability replay guard is in memory.
- For durable incidents, attach a disk at `/var/data` and set
  `GUARDIAN_STATE_PATH=/var/data/guardian/incidents.sqlite3`.

Copy the setting names from `reno_guardian/.env.example` into Render Environment.
Supply your own secrets there. Never commit `.env`, keys, or incident databases.
A Blueprint generates an administrator token; for manual setup supply at least
32 random characters. Retrieve the token privately from Render Environment for
use on the dashboard.

Set `GUARDIAN_PUBLIC_URL` to the service's HTTPS origin, for example
`https://your-service.onrender.com`, without `/api/chat`. Twilio must reach the
`/voice/{id}` WebSocket route. The AI URL must be a complete Chat Completions
endpoint, with a model and API key from the same provider.

Set `GUARDIAN_HEALTH_URL` to your application's externally reachable health endpoint.
Do not point it at Guardian's own health endpoint or localhost. Leave it blank until
verified. Keep `GUARDIAN_CALLS_ENABLED=false` until a controlled voice test succeeds.
The startup command disables access logs to avoid logging voice capability URLs.
Use a private access layer for administrative routes in production while keeping
Twilio's voice route reachable.

Free Render instances are only suitable for temporary testing: they can sleep and
cannot preserve this SQLite database on a persistent disk. On paid instances,
restarts and deployments can still interrupt active calls.

## Current scope

Guardian checks health, stores incidents, suggests investigations, and supports
Twilio ConversationRelay for two-way spoken Tamil. Account eligibility, public
connectivity and live voice quality require acceptance testing. Previous local
phone tests verified fixed-message playback, not the complete two-way integration.
Approvals are recorded but do not execute code changes or deployments.

## Tests

Install dependencies, then run `python -m unittest reno_guardian.test_guardian -v`.
Tests mock external providers and do not place calls.

See [service documentation](reno_guardian/README.md) for local setup and API details.
