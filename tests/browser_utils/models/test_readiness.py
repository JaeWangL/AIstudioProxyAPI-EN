from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from playwright.async_api import TimeoutError

from browser_utils.models.readiness import (
    close_run_settings_panel,
    read_rendered_model_id,
    verify_rendered_model,
)
from browser_utils.models.request_contract import verify_requested_settings
from browser_utils.models.switcher import switch_ai_studio_model


def controls():
    model = MagicMock()
    model.wait_for = AsyncMock()
    model.is_visible = AsyncMock(return_value=False)
    model.inner_text = AsyncMock(return_value="gemini-3.8-flash")
    toggle = MagicMock()
    toggle.wait_for = AsyncMock()
    toggle.click = AsyncMock()
    page = MagicMock()
    page.locator.side_effect = lambda selector: MagicMock(
        first=toggle if "Toggle run settings" in selector else model
    )
    return page, model, toggle


@pytest.mark.asyncio
@pytest.mark.parametrize("visible", [True, False])
async def test_run_settings_closed_only_when_visible(visible):
    page = MagicMock()
    close = page.locator.return_value.first
    close.is_visible = AsyncMock(return_value=visible)
    close.click = AsyncMock()
    close.wait_for = AsyncMock()
    await close_run_settings_panel(page)
    if visible:
        close.click.assert_awaited_once_with(timeout=5000)
        close.wait_for.assert_awaited_once_with(state="hidden", timeout=5000)
    else:
        close.click.assert_not_awaited()


@pytest.mark.asyncio
async def test_visible_panel_is_not_toggled():
    page, _, toggle = controls()
    assert await read_rendered_model_id(page) == "gemini-3.8-flash"
    toggle.click.assert_not_awaited()


@pytest.mark.asyncio
async def test_collapsed_panel_is_opened_before_model_read():
    page, model, toggle = controls()
    model.wait_for.side_effect = [TimeoutError("collapsed"), None]
    assert await read_rendered_model_id(page) == "gemini-3.8-flash"
    toggle.click.assert_awaited_once()


@pytest.mark.asyncio
async def test_late_panel_is_not_closed():
    page, model, toggle = controls()
    model.wait_for.side_effect = [TimeoutError("loading"), None]
    model.is_visible.return_value = True
    await read_rendered_model_id(page)
    toggle.click.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_panel_fails_closed():
    page, model, toggle = controls()
    model.wait_for.side_effect = TimeoutError("missing")
    toggle.wait_for.side_effect = TimeoutError("missing toggle")
    with pytest.raises(TimeoutError):
        await read_rendered_model_id(page)


@pytest.mark.asyncio
async def test_wrong_rendered_model_is_rejected():
    page, _, _ = controls()
    with pytest.raises(RuntimeError, match="Rendered model mismatch"):
        await verify_rendered_model(page, "gemini-3.7-flash")


@pytest.mark.asyncio
async def test_model_fast_path_must_verify_rendered_state():
    page = MagicMock()
    page.url = "https://aistudio.google.com/prompts/new_chat"
    page.evaluate = AsyncMock(return_value='{"promptModel":"models/gemini-3.8-flash"}')
    with patch(
        "browser_utils.models.switcher.verify_rendered_model",
        new=AsyncMock(side_effect=RuntimeError("wrong model on page")),
    ):
        assert not await switch_ai_studio_model(page, "gemini-3.8-flash", "test123")


@pytest.mark.asyncio
@pytest.mark.parametrize("actual,success", [("0", True), ("1", False)])
async def test_zero_temperature_readback(actual, success):
    page = MagicMock()
    control = page.locator.return_value.first
    control.wait_for = AsyncMock()
    control.input_value = AsyncMock(return_value=actual)
    if success:
        await verify_requested_settings(page, {"temperature": 0})
    else:
        with pytest.raises(RuntimeError, match="temperature"):
            await verify_requested_settings(page, {"temperature": 0})


@pytest.mark.asyncio
async def test_missing_requested_setting_is_not_success():
    page = MagicMock()
    page.locator.return_value.first.wait_for = AsyncMock(
        side_effect=TimeoutError("missing")
    )
    with pytest.raises(TimeoutError):
        await verify_requested_settings(page, {"max_output_tokens": 4096})


@pytest.mark.asyncio
async def test_thinking_level_mismatch_is_rejected():
    page = MagicMock()
    page.locator.return_value.first.is_visible = AsyncMock(return_value=True)
    page.locator.return_value.first.inner_text = AsyncMock(return_value="High")
    with pytest.raises(RuntimeError, match="thinking level"):
        await verify_requested_settings(page, {"reasoning_effort": "low"})


@pytest.mark.asyncio
async def test_gemini3_missing_thinking_control_is_rejected():
    page = MagicMock()
    page.locator.return_value.first.wait_for = AsyncMock(
        side_effect=TimeoutError("missing thinking dropdown")
    )
    with pytest.raises(TimeoutError):
        await verify_requested_settings(
            page, {"reasoning_effort": "low"}, "gemini-3.8-flash"
        )
