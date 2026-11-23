# Event registration API

Flask API for the `users`, `events`, and `registrations` tables shown in the
database diagram.

## Run

From the `backend` directory, create the virtual environment and install the
dependencies:

```powershell
py -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

Create a `.env` file with the Supabase project values:

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_PUBLISHABLE_KEY=your-publishable-key
```

Then start the server:

```powershell
.\venv\Scripts\python.exe -m flask --app app run --debug
```

## Deploy on Render

This repository includes a `render.yaml` Blueprint. Create a new Render
Blueprint from the repository; Render installs `requirements.txt` and starts
the API with Gunicorn on its assigned `PORT`.

Set these required environment variables in the Render service:

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_PUBLISHABLE_KEY=your-publishable-key
```

Render uses `GET /health` for its health check. Do not commit the local `.env`
file or a virtual-environment directory.

In VS Code, select the `backend\venv\Scripts\python.exe` interpreter if the
editor still reports unresolved imports.

## API

| Method | Endpoint | Notes |
| --- | --- | --- |
| `GET` | `/api/events` | Optional `status`, `limit` (1-100), and `offset`. |
| `GET` | `/api/events/{id}` | Returns a single event. |
| `POST` | `/api/registrations` | JSON body: `user_id`, `event_id`. Returns `201` or `409`. |
| `GET` | `/api/me/registrations?user_id={uuid}` | Registrations for the supplied user, including event details. |
| `GET` | `/api/events/{id}/registrations?organizer_id={uuid}` | Event attendee list, including user details. |

Example registration:

```json
{
  "user_id": "f0c1e2d3-1111-4222-8333-444444444444",
  "event_id": "a0b1c2d3-5555-4666-8777-888888888888"
}
```

## Temporary no-auth behavior

`user_id` and `organizer_id` are explicitly supplied because authentication is
not part of this version. This is **not secure**: anyone who knows an ID can
act as that user or organizer. Add authentication and row-level security before
deploying this API publicly.

For reliable duplicate prevention under concurrent requests, add a database
unique constraint on `(user_id, event_id)`. Capacity enforcement here is an
application-level check; a production version should make it transactional in
the database.
