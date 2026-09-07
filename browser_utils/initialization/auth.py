# --- browser_utils/initialization/auth.py ---
"""
Authentication Saving Module - Simplified Version

Handles saving authentication state after login. Automatically saves to SAVED_AUTH_DIR.
"""

import asyncio
import logging
import os
import tempfile
import time
from pathlib import Path

from config import SAVED_AUTH_DIR

logger = logging.getLogger("AIStudioProxyServer")


async def wait_for_model_list_and_handle_auth_save(temp_context, launch_mode, loop):
    """Wait for model list response and handle authentication saving"""
    from api_utils.server_state import state

    # Wait for model list response to confirm login success
    logger.info("Waiting for model list response to confirm login success...")
    try:
        await asyncio.wait_for(state.model_list_fetch_event.wait(), timeout=30.0)
        logger.info("Model list response detected, login confirmed!")
    except asyncio.TimeoutError:
        logger.warning(
            "Timeout waiting for model list response, but continuing with auth save..."
        )

    # Determine filename: env var > auto-generate
    filename = os.environ.get("SAVE_AUTH_FILENAME", "").strip()
    if not filename:
        filename = f"auth_auto_{int(time.time())}"

    await _save_auth_state(temp_context, filename)


async def _save_auth_state(temp_context, filename: str):
    """Save only this browser context, atomically and with owner-only access."""
    if not filename or filename in {".", ".."} or "/" in filename or "\\" in filename:
        raise ValueError("Authentication profile must be a filename, not a path")
    os.makedirs(SAVED_AUTH_DIR, mode=0o700, exist_ok=True)
    os.chmod(SAVED_AUTH_DIR, 0o700)

    if not filename.endswith(".json"):
        filename += ".json"
    auth_save_path = os.path.join(SAVED_AUTH_DIR, filename)

    print("\n" + "=" * 50, flush=True)
    print("Login successful! Saving authentication state...", flush=True)

    temporary_path = None
    try:
        fd, temporary_path = tempfile.mkstemp(prefix=".auth-", dir=SAVED_AUTH_DIR)
        os.close(fd)
        await temp_context.storage_state(path=temporary_path)
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, auth_save_path)
        logger.info(f"Authentication state saved to: {auth_save_path}")
        print(f"Authentication state saved to: {auth_save_path}", flush=True)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"Failed to save authentication state: {e}", exc_info=True)
        print(f"Failed to save authentication state: {e}", flush=True)
    finally:
        if temporary_path:
            Path(temporary_path).unlink(missing_ok=True)

    print("=" * 50 + "\n", flush=True)
