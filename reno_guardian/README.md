# Reno Guardian

An independent first version of the Reno application monitor. The application
database is never connected by this service. Incidents and approvals live in
its own SQLite file.

## Implemented

- Periodic HTTP health and latency checks, three-failure threshold and recovery.
- Authenticated event ingestion for application, chat, database and CI collectors.
- Persistent deduplicated incidents and audit events.
- Optional model-based investigation and Tamil incident conversation.
- Twilio ConversationRelay outbound calls to one configured owner number.
  Speech interrupts the assistant's pending answer. The call is limited to five minutes.
- Approval records bound to a proposal hash, expiring after one hour.
  New proposals supersede earlier pending or approved suggestions.
- Call reservations prevent automatic duplicate calls after ambiguous failures.

## Current boundaries

This version generates investigation suggestions. It does not create or test code
patches, deploy changes, or execute approved proposals. The API response explicitly
reports that deployment integration is required. Production activation, browser
source-code investigation tools, authenticated application collectors,
regression-test execution, release and rollback adapters remain to be built.
The browser review page is available at the service root. Phone and model adapters
need real-provider acceptance testing. Tamil quality and
interruption latency must be tested on the recipient's phone. Optional provider
failures are recorded locally. A separate external uptime check is required to
detect failure of Guardian itself.

## Local setup

From the repository root, create a dedicated environment and install
`reno_guardian/requirements.txt`. Copy the settings in `.env.example` into the
service environment. The file is a template and is not loaded automatically.
Use a randomly generated administrator token of at least 32 characters.

```powershell
python -m venv .guardian-venv
.guardian-venv/Scripts/python -m pip install -r reno_guardian/requirements.txt
.guardian-venv/Scripts/python -m uvicorn reno_guardian.app:app --host 127.0.0.1 --port 8095 --workers 1
```

Run exactly one worker for this version. Put the persistent state on a protected
local volume. Use a supervised service on an always-on host for continuous operation.
Expose only the voice WebSocket through a TLS proxy with WebSocket support.
Keep administrative endpoints behind a private network and bearer authentication.
Disable proxy query-string logging for voice URLs, which contain a short-lived
incident capability. Use an explicit HTTPS model endpoint for any remote model.

## API usage

Administrative endpoints require `Authorization: Bearer <GUARDIAN_ADMIN_TOKEN>`.

- `GET /health` is the independent liveness endpoint.
- `GET /incidents` returns recent incidents.
- `POST /events` accepts fingerprint, title, evidence and severity
  (`info`, `warning`, `critical`). Send sanitized diagnostics only.
- `POST /incidents/{id}/investigate` creates a suggested investigation.
- `GET /proposals` lists proposals including their digest and expiration.
- `POST /proposals/{id}/approve` accepts `{"digest":"the reviewed digest"}`.
  Approval records consent to that proposal. It does not execute it.

Keep ingestion credentials server-side. Do not embed administrator credentials
in React or expose unrestricted chat text. The current sanitizer catches common
credential formats but does not provide comprehensive personal-data removal.

## Voice

Enable Twilio ConversationRelay on the provider account, configure an eligible
caller number, the owner's E.164 number, and the public HTTPS origin.
Set `GUARDIAN_CALLS_ENABLED=true` only after those settings are verified.
Critical incidents reserve one call per open incident. Recovery permits a new call
for a later recurrence. Failed calls require operator review in the local audit
table rather than automated paid retries.

Voice starts with an AI introduction. The model uses a bounded conversational
history and has no mutation tools. Voice agreement never approves a proposal.
The default conversation style is everyday spoken Tamil from Tamil Nadu, with
familiar English technical terms. Greetings and fallback messages use the same
style. The assistant changes language only when the caller explicitly requests it.
The live bridge uses Tamil locale ta-IN, Google transcription with the long model,
and a configurable Google Tamil voice (default `ta-IN-Chirp3-HD-Aoede`). Verify your
account supports that combination and evaluate naturalness in a live call.
Partial caller speech is assembled before answering. Interruptions retain only
the assistant speech that Twilio reports was heard. Replies use short conversational turns.
`GUARDIAN_PUBLIC_URL` must be the HTTPS origin forwarding to this service, not your
application's chat API. The `/voice/{id}` WebSocket route must be reachable from Twilio.
`GUARDIAN_LLM_URL` must accept the Chat Completions request and response format used
by this service; an unrelated `/api/chat` endpoint is not interchangeable.

## Checks

```powershell
python -m unittest reno_guardian.test_guardian -v
```

Tests cover deduplication, recovery, single-use approval, expiration, changed
proposals, credential redaction and unauthorized API and voice access.

## Reference

OpenJarvis was consulted for its separation of continuous agents, tools and traces.
No OpenJarvis source was copied or installed.

- https://github.com/open-jarvis/OpenJarvis
- https://www.twilio.com/docs/voice/twiml/connect/conversationrelay
- https://www.twilio.com/docs/voice/conversationrelay/websocket-messages
