"""Unauthenticated event-registration API backed by Supabase.

Until authentication is added, endpoints that would normally infer the caller
from a session require an explicit ``user_id`` or ``organizer_id``.  These IDs
are only a temporary routing convention--they are not authorization.
"""

import os
from uuid import UUID

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from postgrest import APIError
from supabase import Client, create_client

load_dotenv()

app = Flask(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_PUBLISHABLE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY must be set in .env")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def error(message: str, status: int):
    return jsonify({"error": message}), status


def required_uuid(value, field_name: str):
    """Return a canonical UUID string, or ``None`` for invalid input."""
    if not value:
        return None
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError):
        return None


def api_error(_exception):
    # Do not expose Supabase internals or credentials through this public API.
    return error("Database request failed", 502)


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/api/events")
def list_events():
    """Browse events. Optional query parameters: status, limit, offset."""
    status = request.args.get("status")
    try:
        limit = min(max(int(request.args.get("limit", 50)), 1), 100)
        offset = max(int(request.args.get("offset", 0)), 0)
    except ValueError:
        return error("limit and offset must be integers", 400)

    query = supabase.table("events").select("*")
    if status:
        query = query.eq("status", status)
    response = query.order("title").range(offset, offset + limit - 1).execute()
    return jsonify(response.data)


@app.get("/api/events/<event_id>")
def get_event(event_id):
    event_id = required_uuid(event_id, "event_id")
    if not event_id:
        return error("event_id must be a UUID", 400)

    response = supabase.table("events").select("*").eq("id", event_id).execute()
    if not response.data:
        return error("Event not found", 404)
    return jsonify(response.data[0])


@app.post("/api/registrations")
def create_registration():
    """Register a user once for an event, returning 409 for duplicates/full events."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return error("Request body must be JSON", 400)

    user_id = required_uuid(payload.get("user_id"), "user_id")
    event_id = required_uuid(payload.get("event_id"), "event_id")
    if not user_id or not event_id:
        return error("user_id and event_id must be UUIDs", 400)

    event_response = supabase.table("events").select("id,capacity,status").eq("id", event_id).execute()
    if not event_response.data:
        return error("Event not found", 404)
    event = event_response.data[0]
    if event.get("status") and event["status"].lower() not in {"open", "published", "active"}:
        return error("Event is not open for registration", 409)

    duplicate = (
        supabase.table("registrations")
        .select("id")
        .eq("user_id", user_id)
        .eq("event_id", event_id)
        .limit(1)
        .execute()
    )
    if duplicate.data:
        return error("User is already registered for this event", 409)

    registrations = supabase.table("registrations").select("id", count="exact").eq("event_id", event_id).execute()
    if event.get("capacity") is not None and (registrations.count or 0) >= event["capacity"]:
        return error("Event is at capacity", 409)

    created = supabase.table("registrations").insert({"user_id": user_id, "event_id": event_id}).execute()
    return jsonify(created.data[0]), 201


@app.get("/api/me/registrations")
def my_registrations():
    # Temporary unauthenticated substitute for the eventual authenticated user.
    user_id = required_uuid(request.args.get("user_id"), "user_id")
    if not user_id:
        return error("user_id query parameter must be a UUID", 400)

    response = (
        supabase.table("registrations")
        .select("*,events(*)")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    return jsonify(response.data)


@app.get("/api/events/<event_id>/registrations")
def event_registrations(event_id):
    """List attendees when organizer_id matches the event's organizer_id.

    This is deliberately only a temporary convention. Add real authentication
    before treating this endpoint as private.
    """
    event_id = required_uuid(event_id, "event_id")
    organizer_id = required_uuid(request.args.get("organizer_id"), "organizer_id")
    if not event_id or not organizer_id:
        return error("event_id and organizer_id must be UUIDs", 400)

    event_response = (
        supabase.table("events")
        .select("id,organizer_id")
        .eq("id", event_id)
        .execute()
    )
    if not event_response.data:
        return error("Event not found", 404)
    if event_response.data[0]["organizer_id"] != organizer_id:
        return error("Only the event organizer can view registrations", 403)

    response = (
        supabase.table("registrations")
        .select("*,users(id,email,role)")
        .eq("event_id", event_id)
        .order("created_at")
        .execute()
    )
    return jsonify(response.data)


app.register_error_handler(APIError, api_error)


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG") == "1",
    )
