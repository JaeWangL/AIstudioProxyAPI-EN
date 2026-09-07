"""The main submission path must preserve prompt text and submit at most once."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from playwright.async_api import TimeoutError

from browser_utils.page_controller import PageController
from models import ClientDisconnectedError


@pytest.fixture
def entry():
    page = MagicMock()
    control = page.locator.return_value
    control.fill = AsyncMock()
    control.input_value = AsyncMock()
    control.click = AsyncMock()
    controller = PageController(page, MagicMock(), "entry-fixture")
    controller._open_upload_menu_and_choose_file = AsyncMock(return_value=True)
    with (
        patch("browser_utils.page_controller.close_run_settings_panel", AsyncMock()),
        patch("browser_utils.page_controller.check_quota_limit", AsyncMock()),
        patch("browser_utils.page_controller.expect_async") as expect,
    ):
        expect.return_value.to_be_visible = AsyncMock()
        expect.return_value.to_be_enabled = AsyncMock()
        yield controller, control


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "prompt", ["reply with exactly OK.", "한글\n\\frac{1}{2} 🙂 e\u0301\t ", ""]
)
async def test_exact_text_readback_and_one_run(entry, prompt):
    controller, control = entry
    control.input_value.return_value = prompt
    await controller.submit_prompt(prompt, ["fixture.png"], lambda stage: False)
    control.fill.assert_awaited_once_with(prompt, timeout=10000)
    assert control.input_value.await_count == 2
    control.click.assert_awaited_once_with(timeout=5000)
    assert control.method_calls[-2:] == [
        call.input_value(timeout=5000),
        call.click(timeout=5000),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("readbacks", [["altered"], ["exact", "changed after upload"]])
async def test_mismatch_never_submits_or_retypes(entry, readbacks):
    controller, control = entry
    control.input_value.side_effect = readbacks
    with pytest.raises(RuntimeError, match="not submitted"):
        await controller.submit_prompt("exact", ["fixture.png"], lambda stage: False)
    control.click.assert_not_awaited()
    control.fill.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error", [TimeoutError("typing timeout"), asyncio.CancelledError()]
)
async def test_incomplete_entry_never_submits_or_falls_back(entry, error):
    controller, control = entry
    control.fill.side_effect = error
    with pytest.raises(type(error)):
        await controller.submit_prompt("exact", [], lambda stage: False)
    control.fill.assert_awaited_once_with("exact", timeout=10000)
    control.click.assert_not_awaited()


@pytest.mark.asyncio
async def test_disconnect_after_input_never_submits(entry):
    controller, control = entry
    with pytest.raises(ClientDisconnectedError):
        await controller.submit_prompt(
            "exact", [], lambda stage: stage == "After Input Fill"
        )
    control.click.assert_not_awaited()
