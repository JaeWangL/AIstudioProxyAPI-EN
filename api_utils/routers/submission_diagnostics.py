"""Local-only, explicitly enabled status inspection. No browser actions."""

from fastapi import HTTPException, Request

from api_utils.server_state import state
from browser_utils.submission_diagnostics import enabled, read_submission_state


async def submission_diagnostics(request: Request):
    if (
        not enabled()
        or not request.client
        or request.client.host not in {"127.0.0.1", "::1"}
    ):
        raise HTTPException(status_code=404)
    if state.page_instance is None:
        raise HTTPException(status_code=503, detail="Browser page unavailable")
    return await read_submission_state(state.page_instance, state.network_log)
