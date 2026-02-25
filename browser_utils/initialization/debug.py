# --- browser_utils/initialization/debug.py ---
import logging
from typing import Any, Set

from playwright.async_api import Page as AsyncPage

logger = logging.getLogger("AIStudioProxyServer")

# Browser console messages can be very long (especially CSP directives)
# so keep warning logs readable while preserving details in state.console_logs.
_MAX_WARNING_LOG_TEXT_LENGTH = 700


def _truncate_for_log(text: str, max_len: int = _MAX_WARNING_LOG_TEXT_LENGTH) -> str:
    """Trim oversized browser-console messages for readable warning logs."""
    if len(text) <= max_len:
        return text
    return f"{text[:max_len]}... [truncated {len(text) - max_len} chars]"


def _is_cookie_attribute_warning(text_lower: str) -> bool:
    """Return True when message matches known benign Google cookie warnings."""
    return "cookie" in text_lower and "rejected for invalid characters" in text_lower


def _is_csp_console_warning(text_lower: str) -> bool:
    """Return True when message is a CSP browser-console warning from AI Studio page."""
    return "content-security-policy" in text_lower


def _build_csp_signature(text_lower: str) -> str:
    """
    Build a low-cardinality signature for duplicate suppression.

    CSP console lines contain varying URLs, so we normalize by policy/directive markers.
    """
    policy_scope = "report-only" if "report-only" in text_lower else "enforced"
    if "script-src-elem" in text_lower:
        return f"csp:{policy_scope}:script-src-elem"
    if "script-src" in text_lower:
        return f"csp:{policy_scope}:script-src"
    return f"csp:{policy_scope}:other"


def _extract_location(msg: Any) -> str:
    """Safely extract console location in '<url>:<line>' format when present."""
    location = getattr(msg, "location", None)
    if not isinstance(location, dict):
        return ""

    url = str(location.get("url", ""))
    line = location.get("lineNumber", 0)
    if url or line:
        return f"{url}:{line}"
    return ""


def setup_debug_listeners(page: AsyncPage) -> None:
    """
    Setup console and network logging listeners for comprehensive error snapshots.

    This function attaches event listeners to capture:
    - Browser console messages (log, warning, error, etc.)
    - Network requests and responses

    Args:
        page: Playwright page instance to attach listeners to
    """
    from datetime import datetime, timezone

    from api_utils.server_state import state

    seen_benign_console_signatures: Set[str] = set()

    def handle_console(msg: Any) -> None:
        """Handle console messages from the browser."""
        try:
            message_text = str(getattr(msg, "text", ""))
            message_type = str(getattr(msg, "type", ""))
            location_str = _extract_location(msg)

            state.console_logs.append(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "type": message_type,
                    "text": message_text,
                    "location": location_str,
                }
            )

            if message_type == "error":
                text_lower = message_text.lower()

                if _is_cookie_attribute_warning(text_lower):
                    logger.debug(
                        "[Browser Cookie Warning] %s - This may indicate the auth profile needs refresh",
                        message_text,
                    )
                    return

                if _is_csp_console_warning(text_lower):
                    signature = _build_csp_signature(text_lower)
                    if signature not in seen_benign_console_signatures:
                        seen_benign_console_signatures.add(signature)
                        logger.debug(
                            "[Browser CSP] Ignoring CSP console message (first occurrence): %s",
                            _truncate_for_log(message_text),
                        )
                    return

                logger.warning("[Browser Console Error] %s", _truncate_for_log(message_text))

        except Exception as e:
            logger.error(f"Failed to capture console message: {e}")

    def handle_request(request: Any) -> None:
        """Handle network requests."""
        try:
            # Only log relevant requests (skip static assets, images, etc.)
            url_lower = request.url.lower()
            if any(
                ext in url_lower
                for ext in [".png", ".jpg", ".jpeg", ".gif", ".css", ".woff", ".woff2"]
            ):
                return  # Skip static assets

            state.network_log["requests"].append(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "url": request.url,
                    "method": request.method,
                    "resource_type": request.resource_type,
                }
            )
        except Exception as e:
            logger.error(f"Failed to capture network request: {e}")

    def handle_response(response: Any) -> None:
        """Handle network responses."""
        try:
            # Only log relevant responses
            url_lower = response.url.lower()
            if any(
                ext in url_lower
                for ext in [".png", ".jpg", ".jpeg", ".gif", ".css", ".woff", ".woff2"]
            ):
                return  # Skip static assets

            state.network_log["responses"].append(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "url": response.url,
                    "status": response.status,
                    "status_text": response.status_text,
                }
            )
        except Exception as e:
            logger.error(f"Failed to capture network response: {e}")

    page.on("console", handle_console)
    page.on("request", handle_request)
    page.on("response", handle_response)

    logger.debug("Debug listeners (console + network) attached to page")
