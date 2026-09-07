"""Opt-in, read-only UI diagnostics. Never inspect credentials or request bodies."""

import asyncio
import json
import os
import re
from urllib.parse import urlsplit

from config import PROMPT_TEXTAREA_SELECTOR, SUBMIT_BUTTON_SELECTOR


def enabled():
    return os.getenv("SUBMISSION_DIAGNOSTICS", "false").lower() == "true"


def rpc_summary(network_log):
    """Only fixed RPC method names/statuses; no query strings, IDs or payloads."""
    result = []
    for item in network_log.get("responses", [])[-100:]:
        url = urlsplit(item.get("url", ""))
        if url.hostname != "alkalimakersuite-pa.clients6.google.com":
            continue
        method = url.path.rsplit("/", 1)[-1]
        if not re.fullmatch(r"[A-Za-z]{1,64}", method):
            continue
        result.append({"rpc": method, "status": item.get("status")})
    return result[-20:]


def error_summary(payload):
    """Extract only standard error enums, never messages/metadata/token values."""
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return {"structured_error": False}
    result = {"structured_error": True}
    code = error.get("code")
    if isinstance(code, int) and 100 <= code <= 599:
        result["code"] = code
    status = error.get("status")
    statuses = {
        "PERMISSION_DENIED",
        "UNAUTHENTICATED",
        "RESOURCE_EXHAUSTED",
        "INVALID_ARGUMENT",
        "INTERNAL",
        "UNAVAILABLE",
    }
    if isinstance(status, str) and status in statuses:
        result["status"] = status
    details = error.get("details", [])
    reasons = []
    if isinstance(details, list):
        for detail in details[:10]:
            if (
                not isinstance(detail, dict)
                or detail.get("@type") != "type.googleapis.com/google.rpc.ErrorInfo"
            ):
                continue
            reason = detail.get("reason")
            if isinstance(reason, str) and re.fullmatch(r"[A-Z][A-Z_]{1,63}", reason):
                reasons.append(reason)
    result["reasons"] = reasons
    return result


async def log_generation_failure(response, logger):
    """Read an already completed failure response, without making another request."""
    if not enabled() or response.status not in {400, 401, 403, 429}:
        return
    url = urlsplit(response.url)
    if (
        url.hostname != "alkalimakersuite-pa.clients6.google.com"
        or url.path.rsplit("/", 1)[-1] != "GenerateContent"
    ):
        return
    try:
        body = await asyncio.wait_for(response.text(), timeout=3)
        if len(body) > 65536:
            logger.info(
                "Generation rejection diagnostic: body exceeds diagnostic bound"
            )
            return
        # Some Google RPC responses have an XSSI prefix, not plain JSON.
        text = body.removeprefix(")]}'\n").strip()
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            logger.info(
                "Generation rejection diagnostic: %s",
                json.dumps(
                    {
                        "structured_error": False,
                        "body_characters": len(body),
                        "format": "html"
                        if text.lower().startswith(("<!doctype html", "<html"))
                        else "other",
                        "automated_queries_notice": "automated queries" in text.lower(),
                        "unusual_traffic_notice": "unusual traffic" in text.lower(),
                    }
                ),
            )
            return
        logger.info(
            "Generation rejection diagnostic: %s", json.dumps(error_summary(payload))
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.info(
            "Generation rejection diagnostic unavailable: %s", type(exc).__name__
        )


async def read_submission_state(page, network_log):
    if urlsplit(page.url).hostname != "aistudio.google.com":
        raise RuntimeError("Diagnostic requires the dedicated AI Studio page")
    data = await asyncio.wait_for(
        page.evaluate(
            """([inputSelector, runSelector]) => {
                const input = document.querySelector(inputSelector);
                const run = document.querySelector(runSelector);
                const rect = run?.getBoundingClientRect();
                const hit = rect ? document.elementFromPoint(
                    rect.x + rect.width / 2, rect.y + rect.height / 2) : null;
                return {
                    ready_state: document.readyState,
                    visibility: document.visibilityState,
                    has_focus: document.hasFocus(),
                    prompt_focused: document.activeElement === input,
                    user_activation_active: navigator.userActivation?.isActive ?? null,
                    user_activation_seen: navigator.userActivation?.hasBeenActive ?? null,
                    input_present: !!input,
                    input_length: input?.value?.length ?? null,
                    run_present: !!run,
                    run_disabled: run ? (run.disabled || run.getAttribute('aria-disabled') === 'true') : null,
                    run_hit_test: !!run && !!hit && (run === hit || run.contains(hit)),
                    page_kind: location.pathname === '/prompts/new_chat' ? 'new_chat' : 'other'
                };
            }""",
            [PROMPT_TEXTAREA_SELECTOR, SUBMIT_BUTTON_SELECTOR],
        ),
        timeout=3,
    )
    return {**data, "rpc_responses": rpc_summary(network_log)}


async def log_submission_state(page, logger, req_id, stage):
    if not enabled():
        return
    from api_utils.server_state import state

    try:
        data = await read_submission_state(page, state.network_log)
        logger.info(
            "[%s] Submission diagnostic %s: %s", req_id, stage, json.dumps(data)
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning(
            "[%s] Submission diagnostic unavailable: %s", req_id, type(exc).__name__
        )
