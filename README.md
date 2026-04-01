# Child Care — API & Realtime Server (Backend)

Flask application providing REST APIs, JWT authentication, MongoDB persistence, GridFS-backed files, Socket.IO realtime channels, and integrations (Metered video rooms, optional OpenAI for summaries and clinical documentation). It powers the **child-care** web client for telehealth workflows, patient records, notifications, AI-assisted documentation with governance hooks, and administrative operations.

## Tech stack

| Area | Technology |
|------|------------|
| Framework | Flask, flask-openapi3 |
| Auth | Flask-JWT-Extended |
| Database | MongoDB (PyMongo), GridFS for binary assets |
| Realtime | Flask-SocketIO |
| Validation | Pydantic |
| Rate limiting | Flask-Limiter (memory or Redis) |
| Observability | Optional Sentry (`sentry-sdk`) |
| HTTP client | `requests` (Metered API, OpenAI) |
| PDF / docs | ReportLab, PyPDF2, etc. (see `requirements.txt`) |

**Entry point:** `main.py` runs the Socket.IO server. Application wiring (app, JWT, blueprints, socket handlers) lives in `src/connector.py`.

## Prerequisites

- **Python** 3.10+ recommended
- **MongoDB** (Atlas or self-hosted) and a connection string
- **Metered** API credentials for creating and joining WebRTC rooms
- Optional: **OpenAI API key** for meeting summaries and Phase 3 clinical documentation
- Optional: **Redis** URL for distributed rate limiting (`RATE_LIMIT_STORAGE_URI`)

## Environment variables

Create `.env` in the project root (`python-dotenv` loads it). Copy from `.env.example`:

```bash
cp .env.example .env
```

### Core

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | MongoDB connection URI |
| `PORT` | No | HTTP port (default `8000`) |
| `JWT_SECRET_KEY` | Yes (production) | Secret for signing JWTs; also used with room/socket token helpers. Avoid dev defaults in production. |
| `JWT_SECRET` | No | Legacy alias if `JWT_SECRET_KEY` is unset |
| `METERED_SECRET_KEY` | Yes* | Metered API secret for room creation |
| `METERED_DOMAIN` | Yes* | Metered hostname used in API calls |

\*Required for full video room flows.

### Security and operations

| Variable | Description |
|----------|-------------|
| `ADMIN_BOOTSTRAP_SECRET` | When set, the **first** admin account must be created with header `X-Admin-Bootstrap: <secret>`. Further admin creation requires an admin JWT. |
| `RATE_LIMIT_STORAGE_URI` | Default `memory://`. Use e.g. `redis://localhost:6379` for multiple app instances. |
| `SENTRY_DSN` | Optional; enables error and performance monitoring |
| `SENTRY_ENVIRONMENT` | Optional label (e.g. `production`) |
| `SENTRY_TRACES_SAMPLE_RATE` | Optional trace sampling (default `0.1`) |

### AI and clinical documentation (Phase 3)

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | Enables OpenAI-backed text generation |
| `OPENAI_MODEL` | Defaults to `gpt-4o-mini` where applicable |
| `MEETINGS_AI_REQUIRE_CONSENT` | When true, `/api/meetings_ai/generate` requires `consent_documentation: true` |
| `MEETINGS_AI_RETENTION_DAYS` | Retention hint stored on generated reports |

### Other

| Area | Variables |
|------|-----------|
| Email | `SMTP_SERVER`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD` |
| AWS / S3 | `AWS_ACCESS_KEY`, `AWS_SECRET_KEY`, `BUCKET_NAME` (if used) |
| App | `PROD`, `APP_NAME`, `TOKEN_VALIDITY` — see `.env.example` |

**Never commit** `.env`, API keys, or database URLs. Rotate any credential that was ever exposed.

### Socket.IO and MongoDB

Doctor accounts live in the `users` collection. **Socket presence** uses `socket_sessions` (and `private_dm_channels` for DM routing) so disconnect logic does not delete REST user documents. In-room messages are stored with `room_name` / `room_id` as applicable.

### CORS and TLS

- Prefer **TLS** in production.
- Tighten CORS from `*` to known frontend origins when deploying.

## Install and run

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Unix:    source .venv/bin/activate

pip install -r requirements.txt
python main.py
```

The server binds to `0.0.0.0` on `PORT` (see `main.py` / `constants.py`).

## API overview

Blueprints are mounted under `/api/...`:

| Prefix | Purpose |
|--------|---------|
| `/api/users` | Registration, profile, login, JWT “me” |
| `/api/admins` | Admin login, companies/users (JWT), system overview, AI config, governance audit, user directory |
| `/api/room` | Metered-backed rooms, fetch/join, patient/guest checks |
| `/api/events` | Calendar events (including patient-scoped listings) |
| `/api/file_system` | Upload/download, GridFS |
| `/api/patient_records` | Patient profiles and notes |
| `/api/meeting_ai` | Legacy transcript / summary pipeline |
| `/api/meetings_ai` | Phase 3 clinical documentation (Markdown/PDF, consent, audit, optional patient visibility) |
| `/api/notifications` | In-app notifications |
| `/api/waiting_room` | REST helpers; live queue via Socket.IO |

### Health and monitoring

| Endpoint | Auth | Description |
|----------|------|-------------|
| `GET /api/health` | No | Liveness JSON (service name, Sentry flag) |
| `GET /api/monitoring/health` | No | Same contract as above |
| `GET /api/monitoring/ready` | No | Readiness placeholder (extend with DB ping if needed) |
| `GET /api/monitoring/overview` | Admin JWT | Uptime, optional Metered usage (30-day window when credentials set), operational notes |

### Rate limits (selected routes)

Per client IP: user login/register and admin login are limited (see `src/extensions.py` and route decorators). Tune limits and storage for production load.

### Socket.IO events (selected)

Includes room lifecycle, **in-room chat** (`room_message`), DMs, **waiting room** (`join_waiting_room`, `admit_waiting`, `reject_waiting`, `waiting_room_update`, `admission_granted`, `admission_denied`), and chat history.

## Operations

### MongoDB backups

Use **`ops/mongodb-backup.sh`** with environment variables `MONGODB_URI` (same as `DATABASE_URL`) and `BACKUP_DIR`. Requires [MongoDB Database Tools](https://www.mongodb.com/try/download/database-tools) (`mongodump`).

## Project layout

```
src/
  connector.py          # App, JWT, CORS, limiter, Sentry, blueprints, Socket.IO
  extensions.py         # Flask-Limiter instance
  modules/              # Feature modules (user, room, admin, meetings_ai, …)
  utils/                # Helpers, socket/JWT utilities
constants.py            # Environment-backed constants
main.py                 # Server entry (socketio.run)
ops/
  mongodb-backup.sh     # Optional mongodump wrapper
```

## Testing

```bash
pytest
```

Tests may live alongside modules as `*_test.py` or under `tests/` where present.

## License

Private / unlicensed unless otherwise specified by the project owners.
