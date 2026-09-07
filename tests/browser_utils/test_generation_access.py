from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from api_utils.server_state import state
from browser_utils.generation_access import (
    ensure_generation_access,
    track_generation_response,
)


@pytest.fixture(autouse=True)
def isolated_access(mock_server_state):
    with (
        patch("api_utils.server_state.state", state),
        patch.object(state, "generation_access", {"status": "unknown"}),
    ):
        yield


def response(
    status, method="GenerateContent", host="alkalimakersuite-pa.clients6.google.com"
):
    return MagicMock(status=status, url=f"https://{host}/$rpc/Service/{method}")


def test_denial_latches_until_successful_ui_request():
    ensure_generation_access()
    track_generation_response(response(403))
    with pytest.raises(HTTPException) as exc:
        ensure_generation_access()
    assert exc.value.status_code == 403
    assert exc.value.detail["retryable"] is False
    track_generation_response(response(200, "CountTokens"))
    assert state.generation_access["status"] == "denied"
    track_generation_response(response(200))
    assert state.generation_access["status"] == "accepted"
    ensure_generation_access()


@pytest.mark.parametrize(
    "code,method,host",
    [
        (429, "GenerateContent", "alkalimakersuite-pa.clients6.google.com"),
        (403, "ListModels", "alkalimakersuite-pa.clients6.google.com"),
        (403, "GenerateContent", "example.com"),
    ],
)
def test_only_generation_permission_denial_latches(code, method, host):
    track_generation_response(response(code, method, host))
    assert state.generation_access == {"status": "unknown"}


def test_ui_permission_denial_latches_without_network_evidence():
    from browser_utils.generation_access import mark_ui_permission_denied

    mark_ui_permission_denied()
    assert state.generation_access["status"] == "denied"
    assert state.generation_access["evidence"] == "ui_permission_denied"
    assert "http_status" not in state.generation_access


@pytest.mark.asyncio
async def test_health_does_not_advertise_generation_ready_after_denial():
    import json
    from asyncio import Queue

    from api_utils.routers.health import health_check

    track_generation_response(response(403))
    worker = MagicMock()
    worker.done.return_value = False
    result = await health_check(
        server_state={
            "is_initializing": False,
            "is_playwright_ready": True,
            "is_browser_connected": True,
            "is_page_ready": True,
        },
        worker_task=worker,
        request_queue=Queue(),
    )
    assert result.status_code == 503
    assert json.loads(result.body)["details"]["generationAccess"]["status"] == "denied"


@pytest.mark.asyncio
async def test_queued_submission_does_not_touch_browser_after_denial():
    from browser_utils.page_controller import PageController

    track_generation_response(response(403))
    page = MagicMock()
    controller = PageController(page, MagicMock(), "blocked")
    with pytest.raises(HTTPException):
        await controller.submit_prompt("do not send", [], lambda stage: False)
    page.locator.assert_not_called()


@pytest.mark.asyncio
async def test_denied_api_request_does_not_enter_queue():
    from api_utils.routers.chat import chat_completions
    from models import ChatCompletionRequest

    track_generation_response(response(403))
    queue = MagicMock()
    queue.put = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        await chat_completions(
            ChatCompletionRequest(
                model="gemini-3.8-flash",
                messages=[{"role": "user", "content": "do not send"}],
            ),
            Request({"type": "http"}),
            logger=MagicMock(),
            request_queue=queue,
        )
    assert exc.value.status_code == 403
    queue.put.assert_not_awaited()
