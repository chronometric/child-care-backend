# Child Care — API & Realtime Server (Backend)

A Flask application providing REST APIs, JWT authentication, MongoDB persistence, Socket.IO realtime channels, and integrations (Metered video rooms, optional OpenAI for session summaries). It powers the **child-care** web client for telehealth workflows, patient records, notifications, and administrative operations.

## Tech stack

| Area | Technology |
|------|------------|
| Framework | Flask, flask-openapi3 |
| Auth | Flask-JWT-Extended |
| Database | MongoDB (PyMongo), GridFS for binary assets |
| Realtime | Flask-SocketIO |
| Validation | Pydantic |
| HTTP client | `requests` (Metered API, optional OpenAI) |

Entry point: `main.py` (Socket.IO server). Application wiring lives in `src/connector.py` (app, JWT, blueprints, socket handlers).

## Prerequisites

- **Python** 3.10+ recommended
- **MongoDB** instance (Atlas or self-hosted) and connection string
- **Metered** API credentials for creating and validating meeting rooms
- Optional: **OpenAI API key** for AI-generated session summaries

## Environment variables

Create a `.env` file in the project root (loaded via `python-dotenv`). Typical variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | MongoDB connection URI |
| `PORT` | No | HTTP port (default `8000`) |
| `JWT_SECRET` / app config | See `connector.py` | Align JWT secret with deployment; `connector.py` sets `JWT_SECRET_KEY` for Flask-JWT-Extended |
| `METERED_SECRET_KEY` | Yes | Metered API secret |
| `METERED_DOMAIN` | Yes | Metered domain (used in room creation/validation) |
| `OPENAI_API_KEY` | No | Enables AI summaries in meeting reports |
| `OPENAI_MODEL` | No | Defaults to `gpt-4o-mini` in meeting AI service |
| `PROD`, `APP_NAME`, `TOKEN_VALIDITY` | No | Optional operational flags |
| AWS / S3 | No | `AWS_ACCESS_KEY`, `AWS_SECRET_KEY`, `BUCKET_NAME` if used for uploads |
| SMTP | No | Prefer moving any mail credentials from code into environment variables for production |

### Security

- Do not commit `.env`, API keys, or database URLs.
- Rotate any credentials that were ever checked into source control.
- Use TLS in production and restrict CORS origins instead of `*` when deploying.

## Install and run

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Unix: source .venv/bin/activate

pip install -r requirements.txt
python main.py
```

The server binds to `0.0.0.0` on `PORT` (see `main.py` / `constants.py`).

## API surface (overview)

Blueprints are registered under `/api/...` prefixes, including:

| Prefix | Purpose |
|--------|---------|
| `/api/users` | Registration, profile, JWT user |
| `/api/admins` | Admin auth, companies/users aggregation, system overview, AI config |
| `/api/room` | Metered-backed rooms, join/leave/end, patient/guest checks |
| `/api/events` | Calendar events for doctors |
| `/api/file_system` | File upload/download |
| `/api/patient_records` | Longitudinal patient profiles, notes, meeting links |
| `/api/meeting_ai` | Transcript/summary reports (optional OpenAI) |
| `/api/notifications` | In-app notifications for authenticated users |
| `/api/waiting_room` | REST queue listing for hosts (Socket.IO drives live updates) |

Socket.IO events include room lifecycle, chat, and **waiting room** (`join_waiting_room`, `admit_waiting`, `reject_waiting`, `waiting_room_update`, `admission_granted`, `admission_denied`).

## Project layout (high level)

```
src/
  connector.py          # App factory, blueprints, Socket.IO handlers
  modules/              # Feature modules (user, room, admin, patient_record, …)
  utils/                # Helpers, responders, JWT utilities
constants.py            # Environment-backed constants
main.py                 # Server entry (socketio.run)
```

## Testing

```bash
pytest
```

Tests live under module `*_test.py` files where present.

## License

Private / unlicensed unless otherwise specified by the project owners.
