"""Verify the rendered run settings instead of trusting localStorage flags."""

from playwright.async_api import Page, TimeoutError

from config.selectors import MODEL_NAME_SELECTOR

RUN_SETTINGS_TOGGLE_SELECTOR = 'button[aria-label="Toggle run settings panel"]'


async def read_rendered_model_id(page: Page, timeout: int = 15000) -> str:
    model = page.locator(MODEL_NAME_SELECTOR).first
    try:
        await model.wait_for(state="visible", timeout=min(timeout, 1000))
    except TimeoutError:
        # Current Playground removes the panel contents from the DOM when
        # collapsed. Legacy isAdvancedOpen preferences do not open that panel.
        toggle = page.locator(RUN_SETTINGS_TOGGLE_SELECTOR).first
        await toggle.wait_for(state="visible", timeout=timeout)
        # Re-check after waiting: do not close a panel that loaded meanwhile.
        if not await model.is_visible():
            await toggle.click(timeout=timeout)
        await model.wait_for(state="visible", timeout=timeout)
    model_id = (await model.inner_text(timeout=timeout)).strip()
    if not model_id:
        raise RuntimeError("Run settings are visible but the model identifier is empty")
    return model_id


async def verify_rendered_model(page: Page, expected: str) -> None:
    actual = await read_rendered_model_id(page)
    if actual != expected:
        raise RuntimeError(
            f"Rendered model mismatch: expected {expected!r}, received {actual!r}"
        )


async def close_run_settings_panel(page: Page) -> None:
    """After verification, release the prompt area covered by the responsive panel."""
    close = page.locator('button[aria-label="Close run settings panel"]').first
    if await close.is_visible():
        await close.click(timeout=5000)
        await close.wait_for(state="hidden", timeout=5000)
