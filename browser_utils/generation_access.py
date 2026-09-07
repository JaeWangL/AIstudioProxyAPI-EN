"""Stop automatic submissions after a real provider access denial, not a quota wait."""

from datetime import datetime, timezone
from urllib.parse import urlsplit

from fastapi import HTTPException


def is_generation_response(response):
    url = urlsplit(response.url)
    return (
        url.hostname == "alkalimakersuite-pa.clients6.google.com"
        and url.path.rsplit("/", 1)[-1] == "GenerateContent"
    )


def permission_denied():
    return HTTPException(
        status_code=403,
        detail={
            "code": "aistudio_generation_permission_denied",
            "message": "AI Studio denied generation permission; automatic submissions paused pending human/provider review.",
            "retryable": False,
        },
    )


def track_generation_response(response):
    """Observe existing UI traffic only. A 200 clears denial, not proof of good output."""
    if not is_generation_response(response) or response.status not in {200, 403}:
        return
    from api_utils.server_state import state

    state.generation_access = {
        "status": "denied" if response.status == 403 else "accepted",
        "http_status": response.status,
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }


def ensure_generation_access():
    from api_utils.server_state import state

    if state.generation_access["status"] == "denied":
        raise permission_denied()


def mark_ui_permission_denied():
    from api_utils.server_state import state

    if state.generation_access["status"] != "denied":
        state.generation_access = {
            "status": "denied",
            "evidence": "ui_permission_denied",
            "observed_at": datetime.now(timezone.utc).isoformat(),
        }
