"""Launch the real Camoufox bridge and check a local UI fixture. No Google login/LLM."""

import asyncio
import importlib.metadata
import logging
import os
import re
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def smoke():
    from playwright.async_api import async_playwright

    from browser_utils.models.readiness import read_rendered_model_id
    from browser_utils.page_controller import PageController
    from config.selectors import SUBMIT_BUTTON_SELECTOR

    process = await asyncio.create_subprocess_exec(
        sys.executable,
        __file__,
        "--child",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    try:
        assert process.stdout is not None
        async with async_playwright() as playwright:
            while True:
                line = await asyncio.wait_for(process.stdout.readline(), timeout=45)
                if not line:
                    raise RuntimeError(
                        "Browser bridge exited before reporting an endpoint"
                    )
                match = re.search(r"ws://127\.0\.0\.1:\d+/[^\s\x1b]+", line.decode())
                if match:
                    break
            browser = await playwright.firefox.connect(match.group())
            try:
                page = await browser.new_page()
                await page.set_content("""
                    <button aria-label="Toggle run settings panel"
                      onclick="document.querySelector('#panel').hidden=false">Settings</button>
                    <section id="panel" hidden>
                      <span data-test-id="model-name">gemini-3.8-flash</span>
                      <button aria-label="Close run settings panel"
                        onclick="document.querySelector('#panel').hidden=true">Close</button>
                    </section>
                    <ms-prompt-input-wrapper><textarea aria-label="Enter a prompt"></textarea></ms-prompt-input-wrapper>
                    <input type="file" class="file-input">
                    <ms-run-button><button class="ctrl-enter-submits ms-button-primary"
                      aria-disabled="false" onclick="this.dataset.clicked='yes';this.dataset.clicks=String(Number(this.dataset.clicks||0)+1)">Run</button></ms-run-button>""")
                assert await read_rendered_model_id(page) == "gemini-3.8-flash"
                submit = page.locator(SUBMIT_BUTTON_SELECTOR)
                assert await submit.count() == 1
                controller = PageController(page, logging.getLogger("smoke"), "fixture")
                prompt = "exact fixture prompt\n한글 \\frac{1}{2} 🙂 e\u0301\t "
                await controller.submit_prompt(
                    prompt,
                    [
                        {
                            "name": "fixture.txt",
                            "mimeType": "text/plain",
                            "buffer": b"fixture bytes",
                        }
                    ],
                    lambda stage: False,
                )
                assert await submit.get_attribute("data-clicked") == "yes"
                assert await submit.get_attribute("data-clicks") == "1"
                assert not await page.locator("#panel").is_visible()
                assert await page.locator("textarea").input_value() == prompt
                assert (
                    await page.locator('input[type="file"]').evaluate(
                        "el => el.files.length"
                    )
                    == 1
                )
                assert await read_rendered_model_id(page) == "gemini-3.8-flash"
                print(
                    f"PASS: Playwright {importlib.metadata.version('playwright')}, "
                    f"Camoufox package {importlib.metadata.version('camoufox')}, "
                    f"browser {browser.version}; public server + collapsed panel fixture"
                )
            finally:
                await browser.close()
    finally:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            await asyncio.wait_for(process.communicate(), timeout=10)
        except asyncio.TimeoutError:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await process.communicate()


if __name__ == "__main__":
    if "--child" in sys.argv:
        from camoufox import DefaultAddons
        from camoufox.server import launch_server

        from launcher.browser_server import configure_browser_server

        configure_browser_server()
        launch_server(
            headless=True, host="127.0.0.1", port=0, exclude_addons=list(DefaultAddons)
        )
    else:
        asyncio.run(smoke())
