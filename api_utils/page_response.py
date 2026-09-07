import asyncio
import logging
from typing import Callable

from fastapi import HTTPException
from playwright.async_api import Error as PlaywrightAsyncError
from playwright.async_api import Page as AsyncPage
from playwright.async_api import expect as expect_async

from config import RESPONSE_CONTAINER_SELECTOR, RESPONSE_TEXT_SELECTOR


async def _wait_for_text_or_provider_error(container, element, req_id):
    """Do not wait 90 seconds for markdown when the model turn shows an error."""
    from .error_utils import upstream_error

    text_task = asyncio.create_task(expect_async(element).to_be_attached(timeout=90000))
    error_task = asyncio.create_task(
        container.get_by_text("An internal error has occurred.", exact=True).wait_for(
            state="visible", timeout=90000
        )
    )
    try:
        done, _ = await asyncio.wait(
            {text_task, error_task}, return_when=asyncio.FIRST_COMPLETED
        )
        if error_task in done and error_task.exception() is None:
            raise upstream_error(
                req_id, "AI Studio displayed an internal generation error"
            )
        await text_task
    finally:
        for task in (text_task, error_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(text_task, error_task, return_exceptions=True)


async def locate_response_elements(
    page: AsyncPage,
    req_id: str,
    logger: logging.Logger,
    check_client_disconnected: Callable[[str], bool],
) -> None:
    """Locate response container and text elements, including timeout and error handling."""
    logger.info(f"[{req_id}] Locating response elements...")
    response_container = page.locator(RESPONSE_CONTAINER_SELECTOR).last
    response_element = response_container.locator(RESPONSE_TEXT_SELECTOR)

    try:
        await expect_async(response_container).to_be_attached(timeout=20000)
        check_client_disconnected("After Response Container Attached: ")
        await _wait_for_text_or_provider_error(
            response_container, response_element, req_id
        )
        logger.info(f"[{req_id}] Response elements located.")
    except HTTPException:
        from browser_utils.generation_access import ensure_generation_access
        from browser_utils.submission_diagnostics import log_submission_state

        await log_submission_state(page, logger, req_id, "provider_error")
        from browser_utils.operations import save_error_snapshot

        await save_error_snapshot(f"provider_generation_error_{req_id}")
        # Network evidence remains authoritative if the short-lived toast is gone.
        ensure_generation_access()
        if await page.get_by_text(
            "Failed to generate content: permission denied. Please try again.",
            exact=True,
        ).is_visible():
            from browser_utils.generation_access import (
                mark_ui_permission_denied,
                permission_denied,
            )

            mark_ui_permission_denied()
            raise permission_denied() from None
        raise
    except (PlaywrightAsyncError, asyncio.TimeoutError, AssertionError) as locate_err:
        from browser_utils.generation_access import ensure_generation_access
        from browser_utils.operations import save_error_snapshot

        from .error_utils import upstream_error

        await save_error_snapshot(f"response_location_error_{req_id}")
        ensure_generation_access()

        raise upstream_error(
            req_id, f"Failed to locate AI Studio response elements: {locate_err}"
        )
    except Exception as locate_exc:
        from .error_utils import server_error

        raise server_error(
            req_id, f"Unexpected error while locating response elements: {locate_exc}"
        )
