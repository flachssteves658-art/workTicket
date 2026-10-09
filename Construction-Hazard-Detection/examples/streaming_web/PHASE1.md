# Streaming Web Phase 1 (Frontend/Backend Separation)

## Scope
- Keep `examples/streaming_web/backend` as API/WS service only.
- Keep `examples/streaming_web/frontend` as independent static/Vite frontend.
- Do not change `main.py`, `/upload`, `/apply_ticket_to_site`, DB schema, or ticket contract.

## Frontend endpoint model
Frontend now reads four endpoint categories from a unified config source:

- `platformApiUrl` (DB Management)
- `streamingBackendApiUrl` (Streaming backend HTTP/WS)
- `violationApiUrl` (Violation records + segment APIs)
- `ticketUiUrl` (Ticket UI page URL)

Config priority:
1. `window.__CHD_RUNTIME_CONFIG__` from `public/static/runtime-config.js`
2. `VITE_*` env vars
3. Built-in defaults

## Frontend startup

```powershell
cd examples\streaming_web\frontend
npm install
npm run dev
```

Default dev port: `8888`.

## Frontend dev proxy

`vite.config.js` now defines:

- `/api/platform -> :8005`
- `/api/streaming -> :8800` (HTTP + WS)
- `/api/violation -> :8002`
- `/api -> :8800` (legacy compatibility path)

## Frontend env vars (`.env.example`)

- `VITE_PLATFORM_API_URL`
- `VITE_STREAMING_BACKEND_API_URL`
- `VITE_VIOLATION_API_URL`
- `VITE_TICKET_UI_URL`

## Backend startup

```powershell
uvicorn examples.streaming_web.backend.app:app --host 127.0.0.1 --port 8800 --workers 1
```

Backend depends on shared `examples.auth.lifespan` initialization.

Common required env vars:
- `DATABASE_URL`
- `JWT_SECRET_KEY`
- `REDIS_HOST`
- `REDIS_PORT`
- `REDIS_PASSWORD`

## Minimal local development loop
1. Start MySQL + Redis.
2. Start `db_management` (`:8005`).
3. Start `violation_records` (`:8002`).
4. Start `streaming_web/backend` (`:8800`).
5. Start `streaming_web/frontend` (`:8888`).
6. Open `http://127.0.0.1:8888`.
