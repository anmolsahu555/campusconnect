import hmac
import os
from datetime import datetime
from pathlib import Path
from uuid import UUID

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory, session
from postgrest import APIError
from supabase import Client, create_client
from supabase_auth.errors import AuthApiError
from werkzeug.exceptions import HTTPException

load_dotenv()

PROJECT_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = PROJECT_DIR / "public"

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.getenv("FLASK_SECRET_KEY"),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv(
        "FLASK_SESSION_COOKIE_SECURE",
        "true" if os.getenv("VERCEL") == "1" else "false",
    ).lower() == "true",
    MAX_CONTENT_LENGTH=16 * 1024,
)

supabase_url = os.getenv("SUPABASE_URL")
supabase_publishable_key = os.getenv("SUPABASE_PUBLISHABLE_KEY")
supabase_server_key = os.getenv("SUPABASE_SECRET_KEY") or os.getenv(
    "SUPABASE_SERVICE_ROLE_KEY"
)
# A server-only key stays on the serverless function; it is never sent to the
# browser. The publishable key remains a development fallback only.
supabase_key = supabase_server_key or supabase_publishable_key

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
    """Allow credentialed cross-origin requests only from the configured frontend."""
    if request.path.startswith("/api/auth/"):
        response.headers["Cache-Control"] = "no-store"
    frontend_origin = os.getenv("FRONTEND_ORIGIN")
    if frontend_origin:
        if request.headers.get("Origin") == frontend_origin:
            response.headers["Access-Control-Allow-Origin"] = frontend_origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
    else:
        response.headers["Access-Control-Allow-Origin"] = "*"
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


def organizer_auth_configured() -> bool:
    return all(
        (
            supabase is not None,
            supabase_server_key,
            supabase_url,
            supabase_publishable_key,
            os.getenv("FLASK_SECRET_KEY"),
            os.getenv("CAMPUSCONNECT_ORGANIZER_USERNAME", "").strip(),
            os.getenv("CAMPUSCONNECT_ORGANIZER_EMAIL", "").strip(),
        )
    )


def current_organizer():
    if not organizer_auth_configured():
        return None, error("Organizer sign-in is not configured on this deployment.", 503)

    access_token = session.get("organizer_access_token")
    if not access_token:
        return None, error("Organizer sign-in is required.", 401)

    try:
        response = supabase.auth.get_user(access_token)
    except AuthApiError:
        session.clear()
        return None, error("Organizer session is invalid or expired. Sign in again.", 401)

    user = response.user
    configured_email = os.environ["CAMPUSCONNECT_ORGANIZER_EMAIL"].strip().lower()
    if not user or (user.email or "").strip().lower() != configured_email:
        session.clear()
        return None, error("This account is not authorized to create events.", 403)
    return user, None


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


@app.get("/api/auth/me")
def organizer_session():
    if not organizer_auth_configured():
        return jsonify({"enabled": False, "authenticated": False})
    user, failure = current_organizer()
    if failure:
        if failure[1] == 401:
            return jsonify({"enabled": True, "authenticated": False})
        return failure
    return jsonify(
        {
            "enabled": True,
            "authenticated": True,
            "username": session.get("organizer_username"),
        }
    )


@app.post("/api/auth/login")
def organizer_login():
    if not organizer_auth_configured():
        return error("Organizer sign-in is not configured on this deployment.", 503)

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return error("A JSON request body is required.", 400)
    username = payload.get("username")
    password = payload.get("password")
    configured_username = os.environ["CAMPUSCONNECT_ORGANIZER_USERNAME"].strip()
    configured_email = os.environ["CAMPUSCONNECT_ORGANIZER_EMAIL"].strip()
    if (
        not isinstance(username, str)
        or not isinstance(password, str)
        or not hmac.compare_digest(
            username.strip().encode("utf-8"), configured_username.encode("utf-8")
        )
    ):
        return error("Invalid organizer username or password.", 401)

    try:
        auth_client = create_client(supabase_url, supabase_publishable_key)
        response = auth_client.auth.sign_in_with_password(
            {
                "email": configured_email,
                "password": password,
            }
        )
    except AuthApiError:
        return error("Invalid organizer username or password.", 401)

    user = response.user
    if (
        not user
        or not response.session
        or not user.email_confirmed_at
        or (user.email or "").strip().lower()
        != configured_email.lower()
    ):
        return error("Confirm the organizer email before signing in.", 403)

    try:
        supabase.table("users").upsert(
            {"id": str(user.id), "email": user.email, "role": "organizer"}
        ).execute()
    except APIError as exc:
        return error(exc.message, 502)

    session.clear()
    session["organizer_access_token"] = response.session.access_token
    session["organizer_username"] = configured_username
    return jsonify({"authenticated": True, "username": configured_username})


@app.post("/api/auth/logout")
def organizer_logout():
    if organizer_auth_configured():
        session.clear()
    return jsonify({"ok": True})


@app.post("/api/events")
def create_event():
    organizer, failure = current_organizer()
    if failure:
        return failure

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return error("A JSON request body is required.", 400)

    title = payload.get("title")
    location = payload.get("location")
    event_date = payload.get("event_date")
    category = payload.get("category") or "Campus event"
    description = payload.get("description") or ""
    capacity = payload.get("capacity")
    if (
        not isinstance(title, str)
        or not title.strip()
        or len(title.strip()) > 120
        or not isinstance(location, str)
        or not location.strip()
        or len(location.strip()) > 120
        or not isinstance(event_date, str)
        or not isinstance(category, str)
        or len(category.strip()) > 60
        or not isinstance(description, str)
        or len(description.strip()) > 500
        or isinstance(capacity, bool)
        or not isinstance(capacity, int)
        or not 1 <= capacity <= 10000
    ):
        return error("Provide a title, date, location, category, description, and valid capacity.", 400)
    try:
        datetime.fromisoformat(event_date.replace("Z", "+00:00"))
    except ValueError:
        return error("event_date must be a valid ISO date or timestamp.", 400)

    try:
        created = (
            supabase.table("events")
            .insert(
                {
                    "title": title.strip(),
                    "description": description.strip(),
                    "event_date": event_date,
                    "location": location.strip(),
                    "category": category.strip() or "Campus event",
                    "capacity": capacity,
                    "organizer_id": str(organizer.id),
                    "status": "published",
                }
            )
            .execute()
        )
        return jsonify(created.data[0]), 201
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
