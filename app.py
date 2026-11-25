import os
from pathlib import Path
from uuid import UUID

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
from postgrest import APIError
from supabase import Client, create_client
from werkzeug.exceptions import HTTPException

load_dotenv()

PROJECT_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = PROJECT_DIR / "public"

app = Flask(__name__)

supabase_url = os.getenv("SUPABASE_URL")
# A server-only key stays on the serverless function; it is never sent to the
# browser. The publishable key remains a development fallback only.
supabase_key = (
    os.getenv("SUPABASE_SECRET_KEY")
    or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or os.getenv("SUPABASE_PUBLISHABLE_KEY")
)

# Do not fail during Vercel's function import when project variables have not
# been entered yet. The browser shell and /health remain available and API
# requests receive an actionable 503 response instead of a generic invocation
# error. Add SUPABASE_URL and SUPABASE_SECRET_KEY in Vercel Project Settings.
supabase: Client | None = (
    create_client(supabase_url, supabase_key)
    if supabase_url and supabase_key
    else None
)


@app.after_request
def add_cors_headers(response):
    """Support optional standalone frontend development without credentials."""
    response.headers["Access-Control-Allow-Origin"] = os.getenv("FRONTEND_ORIGIN", "*")
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-User-Id"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


def error(message: str, status: int):
    return jsonify({"error": message}), status


@app.before_request
def require_supabase_for_api():
    if request.path.startswith("/api/") and supabase is None:
        return error(
            "Supabase is not configured. Set SUPABASE_URL and SUPABASE_SECRET_KEY in Vercel.",
            503,
        )


def request_user_id():
    """Read the temporary caller identity used while auth is disabled."""
    user_id = request.headers.get("X-User-Id")
    if not user_id:
        return None, error("X-User-Id header is required while authentication is disabled.", 400)
    try:
        return str(UUID(user_id)), None
    except ValueError:
        return None, error("X-User-Id must be a valid UUID.", 400)


def fetch_event(event_id: str):
    try:
        event = supabase.table("events").select("*").eq("id", event_id).maybe_single().execute()
    except APIError as exc:
        return None, error(exc.message, 502)

    if not event.data:
        return None, error("Event not found.", 404)
    return event.data, None


@app.get("/")
def index():
    """Serve the CampusConnect client locally and from the Render function."""
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.get("/health")
def health_check():
    return jsonify({"status": "ok"})


@app.get("/api/events")
def list_events():
    try:
        response = supabase.table("events").select("*").order("title").execute()
        return jsonify(response.data)
    except APIError as exc:
        return error(exc.message, 502)


@app.get("/api/events/<event_id>")
def get_event(event_id: str):
    try:
        UUID(event_id)
    except ValueError:
        return error("event_id must be a valid UUID.", 400)

    event, failure = fetch_event(event_id)
    return failure or jsonify(event)


@app.post("/api/registrations")
def create_registration():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return error("A JSON request body is required.", 400)

    event_id = payload.get("event_id")
    user_id = payload.get("user_id")
    if not event_id or not user_id:
        return error("event_id and user_id are required.", 400)

    try:
        event_id, user_id = str(UUID(event_id)), str(UUID(user_id))
    except ValueError:
        return error("event_id and user_id must be valid UUIDs.", 400)

    event, failure = fetch_event(event_id)
    if failure:
        return failure
    if event.get("status") != "published":
        return error("Registration is unavailable for this event.", 409)

    try:
        existing = (
            supabase.table("registrations")
            .select("id")
            .eq("event_id", event_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        if existing.data:
            return error("User is already registered for this event.", 409)

        registrations = (
            supabase.table("registrations").select("id", count="exact").eq("event_id", event_id).execute()
        )
        if registrations.count is not None and registrations.count >= event["capacity"]:
            return error("This event is at capacity.", 409)

        created = (
            supabase.table("registrations")
            .insert({"event_id": event_id, "user_id": user_id})
            .execute()
        )
        return jsonify(created.data[0]), 201
    except APIError as exc:
        # A unique (event_id, user_id) constraint should also exist in the database.
        # PostgREST exposes PostgreSQL unique violations as SQLSTATE 23505.
        if getattr(exc, "code", None) == "23505":
            return error("User is already registered for this event.", 409)
        return error(exc.message, 502)


@app.get("/api/me/registrations")
def my_registrations():
    user_id, failure = request_user_id()
    if failure:
        return failure
    try:
        response = (
            supabase.table("registrations")
            .select("id, created_at, event:events(*)")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return jsonify(response.data)
    except APIError as exc:
        return error(exc.message, 502)


@app.get("/api/events/<event_id>/registrations")
def event_registrations(event_id: str):
    try:
        UUID(event_id)
    except ValueError:
        return error("event_id must be a valid UUID.", 400)

    user_id, failure = request_user_id()
    if failure:
        return failure

    event, failure = fetch_event(event_id)
    if failure:
        return failure
    if event["organizer_id"] != user_id:
        return error("Only the event organizer can view registrations.", 403)

    try:
        response = (
            supabase.table("registrations")
            .select("id, created_at, user:users(id, email, role)")
            .eq("event_id", event_id)
            .order("created_at")
            .execute()
        )
        return jsonify(response.data)
    except APIError as exc:
        return error(exc.message, 502)


@app.get("/<path:asset_path>")
def frontend_asset(asset_path: str):
    """Serve static browser assets and fall back to the client application."""
    if asset_path.startswith("api/"):
        return error("Route not found.", 404)
    requested_file = FRONTEND_DIR / asset_path
    if requested_file.is_file():
        return send_from_directory(FRONTEND_DIR, asset_path)
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.errorhandler(404)
def route_not_found(_error):
    return error("Route not found.", 404)


@app.errorhandler(Exception)
def unexpected_error(exc):
    """Keep dependency/network failures from becoming opaque 500 responses."""
    if isinstance(exc, HTTPException):
        return exc
    app.logger.exception("Unhandled request error")
    return error("The backend could not reach its data service.", 502)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)
