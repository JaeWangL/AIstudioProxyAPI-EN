import asyncio
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from browser_utils.page_controller import PageController
from models.chat import ChatCompletionRequest


@pytest.mark.parametrize(
    "field,value",
    [("temperature", 0), ("temperature", 1), ("top_p", 0.95), ("top_k", 40)],
)
def test_gemini38_rejects_explicit_sampling(field, value):
    with pytest.raises(ValidationError, match="explicitly omit"):
        ChatCompletionRequest(model="gemini-3.8-flash", messages=[], **{field: value})


@pytest.mark.parametrize("effort", ["minimal", "none", 2048])
def test_gemini38_rejects_unsupported_thinking(effort):
    with pytest.raises(ValidationError, match="low, medium or high"):
        ChatCompletionRequest(
            model="gemini-3.8-flash", messages=[], reasoning_effort=effort
        )


@pytest.mark.parametrize("effort", [None, "low", "medium", "high"])
def test_gemini38_supported_requests(effort):
    request = ChatCompletionRequest(
        model="gemini-3.8-flash", messages=[], reasoning_effort=effort
    )
    assert request.temperature is None


def test_legacy_sampling_contract_is_unchanged():
    request = ChatCompletionRequest(
        model="gemini-3-flash-preview", messages=[], temperature=0
    )
    assert request.temperature == 0


@pytest.mark.asyncio
async def test_current_native_file_input_does_not_require_localized_menu():
    page = MagicMock()
    native_input = page.locator.return_value
    native_input.count = AsyncMock(return_value=1)
    native_input.set_input_files = AsyncMock()
    controller = PageController(page, MagicMock(), "test123")
    assert await controller._open_upload_menu_and_choose_file(["problem.png"])
    native_input.set_input_files.assert_awaited_once_with(
        ["problem.png"], timeout=15000
    )
    page.expect_file_chooser.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "requested,expected",
    [
        ({}, "medium"),
        ({"reasoning_effort": None}, "medium"),
        ({"reasoning_effort": "low"}, "low"),
        ({"reasoning_effort": "high"}, "high"),
    ],
)
async def test_gemini38_controller_skips_sampling_defaults(requested, expected):
    controller = PageController(MagicMock(), MagicMock(), "test123")
    with ExitStack() as stack:
        methods = {
            name: stack.enter_context(
                patch.object(controller, name, new_callable=AsyncMock)
            )
            for name in (
                "_check_disconnect",
                "_adjust_temperature",
                "_adjust_max_tokens",
                "_adjust_stop_sequences",
                "_adjust_top_p",
                "_ensure_tools_panel_expanded",
                "is_function_calling_enabled",
                "_adjust_url_context",
                "_handle_thinking_budget",
                "_adjust_google_search",
            )
        }
        stack.enter_context(
            patch(
                "browser_utils.page_controller.verify_rendered_model",
                new_callable=AsyncMock,
            )
        )
        readback = stack.enter_context(
            patch(
                "browser_utils.page_controller.verify_requested_settings",
                new_callable=AsyncMock,
            )
        )
        cache = {"reasoning_effort": expected, "max_output_tokens": 1234}
        await controller.adjust_parameters(
            requested, cache, asyncio.Lock(), "gemini-3.8-flash", [], AsyncMock()
        )
        assert cache == {}  # stale settings must not survive a new-chat reset
        methods["_adjust_temperature"].assert_not_awaited()
        methods["_adjust_top_p"].assert_not_awaited()
        assert (
            methods["_handle_thinking_budget"].await_args.args[0]["reasoning_effort"]
            == expected
        )
        assert readback.await_args.args[1]["reasoning_effort"] == expected
        assert "temperature" not in requested
