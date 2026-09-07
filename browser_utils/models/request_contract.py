"""Read back explicitly requested settings; warning-only adjustment is not success."""

import math

from config.selectors import (
    MAX_OUTPUT_TOKENS_SELECTOR,
    TEMPERATURE_INPUT_SELECTOR,
    THINKING_LEVEL_SELECT_SELECTOR,
    TOP_P_INPUT_SELECTOR,
)


async def verify_requested_settings(page, params, model_id=None):
    for name, selector in (
        ("temperature", TEMPERATURE_INPUT_SELECTOR),
        ("max_output_tokens", MAX_OUTPUT_TOKENS_SELECTOR),
        ("top_p", TOP_P_INPUT_SELECTOR),
    ):
        expected = params.get(name)
        if expected is None:
            continue
        control = page.locator(selector).first
        await control.wait_for(state="visible", timeout=5000)
        actual = float(await control.input_value(timeout=3000))
        if not math.isclose(actual, float(expected), rel_tol=0, abs_tol=0.0001):
            raise RuntimeError(
                f"Requested {name}={expected} was not applied (UI={actual})"
            )
    effort = params.get("reasoning_effort")
    if isinstance(effort, str) and effort.lower() in {
        "minimal",
        "low",
        "medium",
        "high",
    }:
        level = page.locator(THINKING_LEVEL_SELECT_SELECTOR).first
        if model_id and model_id.startswith("gemini-3"):
            await level.wait_for(state="visible", timeout=5000)
        if await level.is_visible():
            actual = (await level.inner_text(timeout=3000)).strip().lower()
            if actual != effort.lower():
                raise RuntimeError(
                    f"Requested thinking level {effort!r} was not applied"
                )
