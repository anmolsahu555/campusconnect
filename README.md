# CampusConnect web application

This repository is ready for Render and Vercel as a single Flask deployment:
it serves the CampusConnect frontend from `public/` at `/` and its API from
`/api/*`.

## Local development

Run the service with:

```powershell
.\venv\Scripts\python.exe app.py
```

Then open [http://127.0.0.1:5000](http://127.0.0.1:5000). No separate frontend
server is required.

For the backend to access private tables, add the server-only project secret to
your local `.env` (do not expose or commit it):

```env
SUPABASE_SECRET_KEY=your_secret_key
```

`SUPABASE_SERVICE_ROLE_KEY` is also accepted for legacy projects. The existing
publishable key is used only as a fallback for tables deliberately exposed to
the anonymous Data API role.

## Deploy to Render

This repository includes a `render.yaml` blueprint. Create a new Render
Blueprint from the repository, then set these service environment variables in
Render:

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SECRET_KEY=your_server_only_secret
SUPABASE_PUBLISHABLE_KEY=your_publishable_key
FLASK_SECRET_KEY=generate_a_long_random_value
FLASK_SESSION_COOKIE_SECURE=true
CAMPUSCONNECT_ORGANIZER_USERNAME=choose_a_username
CAMPUSCONNECT_ORGANIZER_EMAIL=organizer_account_email
```

Render installs the packages from `requirements.txt`, starts the service with
Gunicorn, and checks `GET /health` for service health. Do not add the Supabase
secret to source control.

Event publishing requires a verified Supabase Auth session for the organizer
email configured on the server. Create and confirm that account in the Supabase
Auth dashboard, then configure the environment variables below. The organizer
username is an alias mapped to that email, not a Supabase Auth username.

The existing student registration endpoints still use a temporary
`X-User-Id` UUID header. Do not treat those routes as production-ready
authorization.

The browser client is included in `public/` and calls relative API routes, so
it works unchanged locally and on Render. The API also allows cross-origin
requests for optional independent frontend development; set `FRONTEND_ORIGIN`
to the exact frontend origin when using organizer sessions across origins.
When the events API is unavailable or has no events, the client displays
labeled sample events for demonstration. Demo registrations are saved only in
the current browser and are not real reservations.
The Events page opens in public demo organizer mode so visitors can try the
event form. Role and created events are saved only in each visitor's browser,
not in Supabase. For shared publishing, use the separate organizer sign-in
panel, which requires verified Supabase Auth and the server-side allowlist
described below.

## Deploy to Vercel

Import this GitHub repository in Vercel with the repository root set to this
folder. Vercel detects the Flask `app` in `app.py`, serves `public/` through
its CDN, and invokes Flask for API requests. Add these environment variables in
Vercel Project Settings before deploying:

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SECRET_KEY=your_server_only_secret
SUPABASE_PUBLISHABLE_KEY=your_publishable_key
FLASK_SECRET_KEY=generate_a_long_random_value
CAMPUSCONNECT_ORGANIZER_USERNAME=choose_a_username
CAMPUSCONNECT_ORGANIZER_EMAIL=organizer_account_email
```

Use `vercel dev` for local Vercel-runtime testing after installing the Vercel
CLI. The supplied `vercel.json` keeps local virtual-environment files out of
the serverless-function bundle. Add these values in Vercel Project Settings,
not in source control. Create the Supabase Auth user with a new password
directly in the Supabase dashboard and confirm its email before signing in.

## Routes

| Method | Route | Request details |
| --- | --- | --- |
| GET | `/api/events` | Browse events. |
| POST | `/api/events` | Publish an event; requires the configured organizer session. |
| GET | `/api/events/{id}` | Event details. |
| POST | `/api/auth/login` | JSON: `{"username":"...","password":"..."}`. |
| GET | `/api/auth/me` | Check organizer sign-in status. |
| POST | `/api/auth/logout` | Clear the organizer session. |
| POST | `/api/registrations` | JSON: `{"event_id":"uuid","user_id":"uuid"}`. Returns `201` or `409`. |
| GET | `/api/me/registrations` | Requires `X-User-Id`. |
| GET | `/api/events/{id}/registrations` | Requires the organizer's `X-User-Id`. |

## Required database safeguards

This API checks for duplicate registrations and capacity, but concurrent
requests need database enforcement too. Add a unique constraint on
`registrations(event_id, user_id)` and move the capacity check plus insert into
a single transactional database function before serving concurrent traffic.
