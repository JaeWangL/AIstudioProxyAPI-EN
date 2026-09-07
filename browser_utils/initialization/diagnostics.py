"""Private, bounded startup diagnostics; no cookies, storage, or environment dump."""

import asyncio
import json
import logging
import os
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

logger = logging.getLogger("AIStudioProxyServer")


async def capture_initialization_failure(page, stage, error):
    try:
        root = Path(__file__).resolve().parents[2] / "errors_py"
        root.mkdir(mode=0o700, exist_ok=True)
        directory = Path(tempfile.mkdtemp(prefix="startup-", dir=root))
        url = urlsplit(page.url)
        metadata = {
            "stage": stage,
            "error_type": type(error).__name__,
            "page_origin_path": f"{url.scheme}://{url.netloc}{url.path}",
        }
        path = directory / "metadata.json"
        path.write_text(json.dumps(metadata, indent=2))
        path.chmod(0o600)
        # Screenshots can contain account details. Opt in explicitly; never
        # capture login form fields, page HTML, localStorage, or network headers.
        if os.getenv("BROWSER_INIT_SCREENSHOTS", "false").lower() == "true":
            if url.hostname == "aistudio.google.com":
                await page.screenshot(path=str(directory / "page.png"), timeout=5000)
                (directory / "page.png").chmod(0o600)
        logger.error("Startup diagnostic saved locally: %s", directory.name)
    except asyncio.CancelledError:
        raise
    except Exception as diagnostic_error:
        logger.warning("Startup diagnostic failed: %s", type(diagnostic_error).__name__)
