import asyncio
import json
import logging
import random
import re
import time
from asyncio import Event
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any, Optional, cast

from playwright.async_api import Page as AsyncPage

from api_utils.utils_ext.usage_tracker import increment_profile_usage
from config import CHAT_COMPLETION_ID_PREFIX
from config.global_state import GlobalState
from config.settings import FUNCTION_CALLING_DEBUG
from logging_utils import set_request_id
from models import (
    ChatCompletionRequest,
    ClientDisconnectedError,
    QuotaExceededError,
    QuotaExceededRetry,
)

from .common_utils import random_id
from .sse import generate_sse_chunk, generate_sse_stop_chunk
from .utils_ext.stream import use_stream_response
from .utils_ext.tokens import calculate_usage_stats

# Pattern to strip emulated function call text from streamed content.
# This prevents "Request function call: ..." blocks from leaking as assistant text.
_FUNCTION_CALL_TEXT_PATTERN = re.compile(
    r"Request\s+function\s+call:\s*[^\n]+(?:\n(?:Parameters:\s*)?\s*\{[\s\S]*?\})?",
    re.IGNORECASE,
)

# Fallback marker for incomplete/truncated function call blocks in cumulative streams.
_FUNCTION_CALL_START_PATTERN = re.compile(
    r"Request\s+function\s+call\s*:",
    re.IGNORECASE,
)

# Pattern to strip control characters like <ctrl46> from body content.
# These appear in AI Studio's wire format as string delimiters.
# Also captures trailing } or { that may follow control chars (JSON leak artifacts).
_CONTROL_CHAR_PATTERN = re.compile(r"<ctrl\d+>[\}\{]?")


def _clean_body_text(body: str) -> str:
    """Clean body text by removing control characters and JSON artifacts."""
    if not body:
        return body
    return _CONTROL_CHAR_PATTERN.sub("", body)


def _strip_emulated_function_call_text(text: str) -> str:
    """Strip emulated function-call instruction text from response content.

    Handles both complete blocks ("Request function call...Parameters...") and
    partial/incomplete blocks by truncating at the first function-call marker.
    """
    if not text:
        return text

    cleaned = _FUNCTION_CALL_TEXT_PATTERN.sub("", text)
    marker_match = _FUNCTION_CALL_START_PATTERN.search(cleaned)
    if marker_match:
        cleaned = cleaned[: marker_match.start()]

    return cleaned.strip()


def _normalize_function_calls(function_calls: list[Any]) -> list[dict[str, Any]]:
    """Normalize parsed function call objects to dict format used by SSE output."""
    normalized: list[dict[str, Any]] = []

    for call in function_calls:
        name: Optional[str] = None
        params: Any = {}

        if isinstance(call, dict):
            raw_name = call.get("name")
            if isinstance(raw_name, str):
                name = raw_name
            params = call.get("params") or call.get("arguments") or {}
        else:
            raw_name = getattr(call, "name", None)
            if isinstance(raw_name, str):
                name = raw_name
            params = getattr(call, "arguments", None) or getattr(call, "params", {})

        if not name:
            continue

        if not isinstance(params, dict):
            params = {}

        normalized.append({"name": name, "params": params})

    return normalized


def _recover_function_calls_from_emulated_text(text: str) -> list[dict[str, Any]]:
    """Recover function calls from emulated text blocks in content/reasoning."""
    if not text or "Request function call:" not in text:
        return []

    try:
        from api_utils.utils_ext.function_call_response_parser import (
            parse_emulated_function_calls_static,
        )

        parsed_calls = parse_emulated_function_calls_static(text)
        return _normalize_function_calls(parsed_calls)
    except Exception:
        return []


def _apply_parallel_tool_call_policy(
    function_calls: list[dict[str, Any]],
    parallel_tool_calls: Optional[bool],
    req_id: str,
    logger: logging.Logger,
) -> list[dict[str, Any]]:
    """Apply parallel_tool_calls policy to normalized function call list."""
    if not function_calls:
        return function_calls

    if parallel_tool_calls is False and len(function_calls) > 1:
        logger.info(
            f"[{req_id}] parallel_tool_calls=false; trimming {len(function_calls)} tool calls to 1"
        )
        return [function_calls[0]]

    return function_calls


async def resilient_stream_generator(
    req_id: str,
    model_name: str,
    generator_factory: Callable[[Event], AsyncGenerator[str, None]],
    completion_event: Event,
    before_retry_callback: Optional[Callable[[], Awaitable[bool]]] = None,
) -> AsyncGenerator[str, None]:
    """
    Wraps a stream generator with resiliency logic.
    Handles QuotaExceededError by triggering auth rotation and retrying.
    """
    from api_utils.server_state import state

    logger = state.logger
    from browser_utils.auth_rotation import (
        perform_auth_rotation,
        verify_post_rotation_page_ready,
    )

    max_retries = 3
    retry_count = 0

    inner_event = Event()

    try:
        while retry_count <= max_retries:
            try:
                if inner_event.is_set():
                    inner_event.clear()

                async for chunk in generator_factory(inner_event):
                    yield chunk

                return

            except (QuotaExceededError, QuotaExceededRetry) as e:
                retry_count += 1
                if retry_count > max_retries:
                    logger.error(
                        f"[{req_id}] Max retries ({max_retries}) exhausted for quota recovery."
                    )
                    yield f"data: {json.dumps({'error': 'Max retries exhausted for quota recovery.'}, ensure_ascii=False)}\n\n"
                    return

                logger.warning(
                    f"[{req_id}] Quota limit hit during stream: {str(e)}. Initiating rotation (Attempt {retry_count}/{max_retries})..."
                )
                yield f": processing auth rotation (attempt {retry_count})...\n\n"

                rotation_task = asyncio.create_task(
                    perform_auth_rotation(target_model_id=model_name)
                )

                rotation_timeout_seconds = 180
                rotation_start = time.time()
                while not rotation_task.done():
                    if time.time() - rotation_start > rotation_timeout_seconds:
                        logger.error(
                            f"[{req_id}] Rotation timed out after {rotation_timeout_seconds}s. Cancelling rotation task."
                        )
                        rotation_task.cancel()
                        try:
                            await asyncio.wait_for(rotation_task, timeout=5)
                        except asyncio.CancelledError:
                            logger.info(
                                f"[{req_id}] Rotation task cancelled after timeout."
                            )
                        except Exception as cancel_err:
                            logger.warning(
                                f"[{req_id}] Rotation task cancellation produced error: {cancel_err}"
                            )

                        yield f"data: {json.dumps({'error': 'Auth rotation timed out.'}, ensure_ascii=False)}\n\n"
                        return

                    yield ": processing auth rotation...\n\n"
                    await asyncio.sleep(2)

                success = await rotation_task
                if success:
                    # Mark rotation completion time for downstream stream timeout guards.
                    # This ensures retried streams fail fast on no-data conditions.
                    GlobalState.LAST_ROTATION_TIMESTAMP = time.time()

                    # Hard gate: ensure critical UI elements exist after rotation
                    # before retrying stream generation.
                    page_instance = getattr(state, "page_instance", None)
                    if page_instance:
                        post_rotation_ready = await verify_post_rotation_page_ready(
                            page=page_instance,
                            req_id=req_id,
                            max_attempts=2,
                        )
                        if not post_rotation_ready:
                            logger.error(
                                f"[{req_id}] [POST-ROTATION-READY-CHECK] verification failed. Aborting retry to prevent broken automation state."
                            )
                            yield f"data: {json.dumps({'error': 'Post-rotation UI verification failed.'}, ensure_ascii=False)}\n\n"
                            return
                        logger.info(
                            f"[{req_id}] [POST-ROTATION-READY-CHECK] verification passed."
                        )
                    else:
                        logger.warning(
                            f"[{req_id}] [POST-ROTATION-READY-CHECK] no page instance found; proceeding with retry."
                        )

                    if before_retry_callback is not None:
                        try:
                            retry_submitted = await before_retry_callback()
                        except Exception as submit_err:
                            logger.error(
                                f"[{req_id}] [ROTATION-RETRY-SUBMIT] failed with exception: {submit_err}",
                                exc_info=True,
                            )
                            yield f"data: {json.dumps({'error': 'Failed to re-submit prompt after rotation.'}, ensure_ascii=False)}\n\n"
                            return

                        if not retry_submitted:
                            logger.error(
                                f"[{req_id}] [ROTATION-RETRY-SUBMIT] callback returned failure. Aborting retry."
                            )
                            yield f"data: {json.dumps({'error': 'Failed to re-submit prompt after rotation.'}, ensure_ascii=False)}\n\n"
                            return

                        logger.info(
                            f"[{req_id}] [ROTATION-RETRY-SUBMIT] prompt re-submitted after rotation."
                        )

                    logger.info(
                        f"[{req_id}] Auth rotation successful. Retrying stream generation..."
                    )
                    yield ": auth rotation complete, retrying...\n\n"
                    continue
                else:
                    logger.error(f"[{req_id}] Auth rotation failed.")
                    yield f"data: {json.dumps({'error': 'Auth rotation failed.'}, ensure_ascii=False)}\n\n"
                    return
            except Exception:
                raise
    finally:
        if not completion_event.is_set():
            completion_event.set()
            logger.info(f"[{req_id}] Resilient stream completion event set")


async def gen_sse_from_aux_stream(
    req_id: str,
    request: ChatCompletionRequest,
    model_name_for_stream: str,
    check_client_disconnected: Callable[[str], bool],
    event_to_set: Event,
    timeout: float,
    silence_threshold: float = 60.0,
    page: Optional[AsyncPage] = None,
    stream_state: Optional[dict[str, Any]] = None,
) -> AsyncGenerator[str, None]:
    """Auxiliary stream queue -> OpenAI compatible SSE generator."""
    logger = logging.getLogger("AIStudioProxyServer")
    set_request_id(req_id)

    last_reason_pos = 0
    last_body_pos = 0
    chat_completion_id = f"{CHAT_COMPLETION_ID_PREFIX}{req_id}-{int(time.time())}-{random.randint(100, 999)}"
    created_timestamp = int(time.time())

    full_reasoning_content = ""
    full_body_content = ""
    data_receiving = False
    is_response_finalized = False
    finish_reason = "stop"

    has_started_body = False
    skip_terminal_chunks_for_retry = False

    try:
        async for raw_data in use_stream_response(
            req_id,
            timeout=timeout,
            silence_threshold=silence_threshold,
            page=page,
            check_client_disconnected=check_client_disconnected,
            enable_silence_detection=True,
        ):
            data_receiving = True

            if GlobalState.CURRENT_STREAM_REQ_ID and req_id != GlobalState.CURRENT_STREAM_REQ_ID:
                logger.warning(f"[{req_id}] 🧟 Zombie Stream Detected! Terminating.")
                break

            if GlobalState.QUOTA_EXCEEDED_EVENT.is_set():
                raise QuotaExceededRetry("Quota exceeded detected mid-stream.")

            if is_response_finalized:
                logger.warning(
                    f"[{req_id}] ⚠️ Extraneous message received after response finalization. Ignoring."
                )
                continue

            # Holding Pattern for Recovery
            if GlobalState.IS_RECOVERING:
                logger.info(
                    f"[{req_id}] ⏸️ System in Recovery Mode. Holding stream open..."
                )
                recovery_wait_start = time.time()
                while GlobalState.IS_RECOVERING:
                    if time.time() - recovery_wait_start > 120.0:
                        logger.error(f"[{req_id}] ❌ Recovery Timed Out. Aborting.")
                        yield generate_sse_chunk(
                            "\n\n[SYSTEM: Service Recovery Failed. Please retry.]",
                            req_id,
                            model_name_for_stream,
                        )
                        yield generate_sse_stop_chunk(req_id, model_name_for_stream)
                        break
                    yield ": heartbeat\n\n"
                    await asyncio.sleep(1.0)

                if GlobalState.IS_RECOVERING:
                    break
                logger.info(f"[{req_id}] ▶️ Recovery Complete. Resuming stream.")

            if GlobalState.IS_QUOTA_EXCEEDED and not GlobalState.IS_RECOVERING:
                logger.warning(
                    f"[{req_id}] ⚠️ Quota exceeded detected. Waiting for recovery initiation..."
                )
                await asyncio.sleep(1)
                if GlobalState.IS_RECOVERING:
                    continue
                logger.warning(
                    f"[{req_id}] ⛔ Quota exceeded, waiting for worker to pick up signal..."
                )
                await asyncio.sleep(2)
                continue

            try:
                check_client_disconnected(f"Stream generator loop ({req_id}): ")
            except ClientDisconnectedError:
                logger.info(
                    f"[{req_id}] Client disconnected, terminating stream generation"
                )
                if data_receiving and not event_to_set.is_set():
                    event_to_set.set()
                break

            data: Any
            if isinstance(raw_data, str):
                try:
                    data = json.loads(raw_data)
                except json.JSONDecodeError:
                    logger.warning(
                        f"[{req_id}] Failed to parse stream data JSON: {raw_data}"
                    )
                    continue
            elif isinstance(raw_data, dict):
                data = cast(dict[str, Any], raw_data)
            else:
                continue

            if not isinstance(data, dict):
                continue

            typed_data: dict[str, Any] = cast(dict[str, Any], data)
            raw_reason = str(typed_data.get("reason", ""))
            raw_body = _clean_body_text(str(typed_data.get("body", "")))
            done = bool(typed_data.get("done", False))
            function = _normalize_function_calls(
                cast(list[Any], typed_data.get("function", []))
            )

            # Robust recovery: when a retried stream produces no packets/body after
            # a recent rotation, convert timeout completion into a retryable signal.
            if (
                done
                and raw_reason in {"ttfb_timeout", "internal_timeout"}
                and not raw_body.strip()
                and not function
                and not full_reasoning_content.strip()
                and not full_body_content.strip()
            ):
                recently_rotated = (
                    time.time() - GlobalState.LAST_ROTATION_TIMESTAMP < 120.0
                )
                if recently_rotated:
                    logger.warning(
                        f"[{req_id}] Stream ended with '{raw_reason}' right after rotation. Triggering another rotation attempt."
                    )
                    raise QuotaExceededRetry(
                        f"[{req_id}] Post-rotation stream timeout ({raw_reason})"
                    )

            # Sanitize emulated function-call text from reasoning/body before streaming.
            reason = _strip_emulated_function_call_text(raw_reason)
            body = _strip_emulated_function_call_text(raw_body)

            # Recovery path: if content was sanitized and function list is empty,
            # attempt to recover function calls from the raw emulated text.
            if not function:
                if reason != raw_reason:
                    recovered_from_reason = _recover_function_calls_from_emulated_text(
                        raw_reason
                    )
                    if recovered_from_reason:
                        function = recovered_from_reason
                        logger.debug(
                            f"[{req_id}] Recovered function calls from emulated reasoning text"
                        )

                if not function and body != raw_body:
                    recovered_from_body = _recover_function_calls_from_emulated_text(
                        raw_body
                    )
                    if recovered_from_body:
                        function = recovered_from_body
                        logger.debug(
                            f"[{req_id}] Recovered function calls from emulated body text"
                        )

            function = _apply_parallel_tool_call_policy(
                function,
                getattr(request, "parallel_tool_calls", True),
                req_id,
                logger,
            )

            suppress_text_deltas = bool(function)
            reason_for_emit = reason
            body_for_emit = body

            # Safety: once function calls are present in a chunk, do not emit new
            # text deltas from that chunk. This prevents mixed text/tool payloads
            # from leaking prompt/planning artifacts in tool-call responses.
            if suppress_text_deltas:
                reason_for_emit = full_reasoning_content
                body_for_emit = full_body_content
                if FUNCTION_CALLING_DEBUG:
                    logger.debug(
                        f"[{req_id}] Suppressing final text delta because done chunk contains function call(s)"
                    )
            else:
                if reason:
                    full_reasoning_content = reason
                if body:
                    full_body_content = body

            # If sanitization truncated cumulative text, clamp cursor positions
            # to avoid stale offsets and malformed deltas.
            if len(reason_for_emit) < last_reason_pos:
                last_reason_pos = len(reason_for_emit)
            if len(body_for_emit) < last_body_pos:
                last_body_pos = len(body_for_emit)

            # The Latch: Reasoning Handling
            if len(reason_for_emit) > last_reason_pos:
                reason_delta = reason_for_emit[last_reason_pos:]
                if not has_started_body:
                    output = {
                        "id": chat_completion_id,
                        "object": "chat.completion.chunk",
                        "model": model_name_for_stream,
                        "created": created_timestamp,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {
                                    "role": "assistant",
                                    "content": None,
                                    "reasoning_content": reason_delta,
                                },
                                "finish_reason": None,
                            }
                        ],
                    }
                    yield f"data: {json.dumps(output, ensure_ascii=False, separators=(',', ':'))}\n\n"
                last_reason_pos = len(reason_for_emit)

            # The Latch: Body Handling
            if len(body_for_emit) > last_body_pos:
                body_delta = body_for_emit[last_body_pos:]
                # Only stream body content if there's actual content after sanitization
                if body_delta.strip():
                    has_started_body = True
                    output = {
                        "id": chat_completion_id,
                        "object": "chat.completion.chunk",
                        "model": model_name_for_stream,
                        "created": created_timestamp,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {
                                    "role": "assistant",
                                    "content": body_delta,
                                },
                                "finish_reason": None,
                            }
                        ],
                    }
                    yield f"data: {json.dumps(output, ensure_ascii=False, separators=(',', ':'))}\n\n"
                last_body_pos = len(body_for_emit)

            if done:
                is_recovering = GlobalState.IS_RECOVERING
                is_quota_exceeded = GlobalState.IS_QUOTA_EXCEEDED

                if (
                    done
                    and not has_started_body
                    and not is_recovering
                    and not is_quota_exceeded
                ):
                    try:
                        from browser_utils.operations import check_quota_limit

                        if page:
                            await check_quota_limit(page, req_id)
                    except Exception:
                        pass
                    await asyncio.sleep(2.0)
                    is_quota_exceeded = GlobalState.IS_QUOTA_EXCEEDED
                    is_recovering = GlobalState.IS_RECOVERING

                if (
                    not has_started_body
                    and not is_recovering
                    and not is_quota_exceeded
                    and not function
                    and not full_body_content.strip()
                    and not full_reasoning_content.strip()
                ):
                    recently_rotated = (
                        time.time() - GlobalState.LAST_ROTATION_TIMESTAMP < 120.0
                    )
                    if recently_rotated:
                        logger.warning(
                            f"[{req_id}] Empty DONE received shortly after rotation; treating as retryable recovery failure."
                        )
                        raise QuotaExceededRetry(
                            f"[{req_id}] Empty post-rotation completion payload"
                        )

                    # Only show synthetic message when there's truly no content AND no function calls.
                    # In native FC mode, empty body with function calls is expected.
                    fallback_text = (
                        "\n\n*(Model finished thinking but generated no output.)*"
                    )
                    output = {
                        "id": chat_completion_id,
                        "object": "chat.completion.chunk",
                        "model": model_name_for_stream,
                        "created": created_timestamp,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {
                                    "role": "assistant",
                                    "content": fallback_text,
                                },
                                "finish_reason": None,
                            }
                        ],
                    }
                    yield f"data: {json.dumps(output, ensure_ascii=False, separators=(',', ':'))}\n\n"
                    full_body_content += fallback_text
                    has_started_body = True
                elif is_recovering or is_quota_exceeded:
                    while GlobalState.IS_QUOTA_EXCEEDED or GlobalState.IS_RECOVERING:
                        yield ": heartbeat\n\n"
                        await asyncio.sleep(1.0)

                if function:
                    finish_reason = "tool_calls"
                    tool_calls_list = []
                    for func_idx, function_call_data in enumerate(function):
                        if isinstance(function_call_data, dict):
                            tool_calls_list.append(
                                {
                                    "id": f"call_{random_id()}",
                                    "index": func_idx,
                                    "type": "function",
                                    "function": {
                                        "name": function_call_data.get("name", ""),
                                        "arguments": json.dumps(
                                            function_call_data.get("params", {})
                                        ),
                                    },
                                }
                            )
                    choice_item = {
                        "index": 0,
                        "delta": {
                            "tool_calls": tool_calls_list,
                        },
                        "finish_reason": None,
                    }
                else:
                    finish_reason = "stop"
                    choice_item = {
                        "index": 0,
                        "delta": {},
                        "finish_reason": None,
                    }

                output = {
                    "id": chat_completion_id,
                    "object": "chat.completion.chunk",
                    "model": model_name_for_stream,
                    "created": created_timestamp,
                    "choices": [choice_item],
                }
                yield f"data: {json.dumps(output, ensure_ascii=False, separators=(',', ':'))}\n\n"
                is_response_finalized = True
                break

    except (QuotaExceededError, QuotaExceededRetry):
        # Let resilient_stream_generator handle rotation/retry without prematurely
        # finalizing the current SSE stream attempt.
        skip_terminal_chunks_for_retry = True
        raise
    except ClientDisconnectedError:
        logger.info(f"[{req_id}] Client disconnected in stream generator")
        if data_receiving and not event_to_set.is_set():
            event_to_set.set()
    except asyncio.CancelledError:
        if not event_to_set.is_set():
            event_to_set.set()
        raise
    except Exception as e:
        logger.error(f"[{req_id}] Error in stream generator: {e}", exc_info=True)
        try:
            error_chunk = {
                "id": chat_completion_id,
                "object": "chat.completion.chunk",
                "model": model_name_for_stream,
                "created": created_timestamp,
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "role": "assistant",
                            "content": f"\n\n[Error: {str(e)}]",
                        },
                        "finish_reason": "stop",
                    }
                ],
            }
            yield f"data: {json.dumps(error_chunk, ensure_ascii=False, separators=(',', ':'))}\n\n"
        except Exception:
            pass
    finally:
        if skip_terminal_chunks_for_retry:
            logger.info(
                f"[{req_id}] Retryable quota signal propagated; skipping terminal SSE chunks for retry."
            )
        else:
            try:
                usage_stats = calculate_usage_stats(
                    [msg.model_dump() for msg in request.messages],
                    full_body_content,
                    full_reasoning_content,
                )
                total_tokens = usage_stats.get("total_tokens", 0)
                GlobalState.increment_token_count(total_tokens)
                from api_utils.server_state import state

                if (
                    hasattr(state, "current_auth_profile_path")
                    and state.current_auth_profile_path
                ):
                    await increment_profile_usage(
                        state.current_auth_profile_path, total_tokens
                    )

                final_chunk = {
                    "id": chat_completion_id,
                    "object": "chat.completion.chunk",
                    "model": model_name_for_stream,
                    "created": created_timestamp,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": finish_reason}],
                    "usage": usage_stats,
                }
                yield f"data: {json.dumps(final_chunk, ensure_ascii=False, separators=(',', ':'))}\n\n"
            except Exception as usage_err:
                logger.error(f"[{req_id}] Error sending usage stats: {usage_err}")

            yield "data: [DONE]\n\n"

        if not event_to_set.is_set():
            event_to_set.set()

        if stream_state is not None:
            stream_state["has_content"] = bool(
                full_body_content or full_reasoning_content
            )


async def gen_sse_from_playwright(
    page: AsyncPage,
    logger: logging.Logger,
    req_id: str,
    model_name_for_stream: str,
    request: ChatCompletionRequest,
    check_client_disconnected: Callable[[str], bool],
    completion_event: Event,
    prompt_length: int,
    timeout: float,
) -> AsyncGenerator[str, None]:
    """Playwright response -> OpenAI compatible SSE generator."""
    from browser_utils.page_controller import PageController
    from models import ClientDisconnectedError

    set_request_id(req_id)
    data_receiving = False
    try:
        page_controller = PageController(page, logger, req_id)
        # Use get_response_with_function_calls which handles both content and functions
        response_data = await page_controller.get_response_with_function_calls(
            check_client_disconnected, prompt_length=prompt_length, timeout=timeout
        )
        raw_content = _clean_body_text(str(response_data.get("content", "") or ""))
        final_content = _strip_emulated_function_call_text(raw_content)
        function_calls = _normalize_function_calls(
            cast(list[Any], response_data.get("function_calls", []))
        )

        if not function_calls and final_content != raw_content:
            recovered_calls = _recover_function_calls_from_emulated_text(raw_content)
            if recovered_calls:
                function_calls = recovered_calls
                logger.debug(
                    f"[{req_id}] Recovered function calls from Playwright content"
                )

        function_calls = _apply_parallel_tool_call_policy(
            function_calls,
            getattr(request, "parallel_tool_calls", True),
            req_id,
            logger,
        )

        # Safety: when tool calls are present, do not stream textual content.
        # This avoids leaking DOM fallback text or prompt artifacts in mixed responses.
        if function_calls:
            final_content = ""

        data_receiving = True
        lines = final_content.split("\n")
        for line_idx, line in enumerate(lines):
            try:
                check_client_disconnected(
                    f"Playwright stream generator loop ({req_id}): "
                )
            except ClientDisconnectedError:
                if data_receiving and not completion_event.is_set():
                    completion_event.set()
                break
            if line:
                chunk_size = 5
                for i in range(0, len(line), chunk_size):
                    yield generate_sse_chunk(
                        line[i : i + chunk_size], req_id, model_name_for_stream
                    )
                    await asyncio.sleep(0.03)
            if line_idx < len(lines) - 1:
                yield generate_sse_chunk("\n", req_id, model_name_for_stream)
                await asyncio.sleep(0.01)

        usage_stats = calculate_usage_stats(
            [msg.model_dump() for msg in request.messages], final_content, ""
        )
        total_tokens = usage_stats.get("total_tokens", 0)
        GlobalState.increment_token_count(total_tokens)
        from api_utils.server_state import state

        if (
            hasattr(state, "current_auth_profile_path")
            and state.current_auth_profile_path
        ):
            await increment_profile_usage(state.current_auth_profile_path, total_tokens)

        if function_calls:
            from api_utils.utils_ext.function_calling_orchestrator import (
                get_function_calling_orchestrator,
            )

            orchestrator = get_function_calling_orchestrator()
            tool_calls_deltas = orchestrator.format_streaming_tool_calls(function_calls)
            for delta in tool_calls_deltas:
                chunk = {
                    "id": f"chatcmpl-{req_id}",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": model_name_for_stream,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"tool_calls": [delta]},
                            "finish_reason": None,
                        }
                    ],
                }
                yield f"data: {json.dumps(chunk, ensure_ascii=False, separators=(',', ':'))}\n\n"

            yield generate_sse_stop_chunk(
                req_id, model_name_for_stream, "tool_calls", usage_stats
            )
        else:
            yield generate_sse_stop_chunk(
                req_id, model_name_for_stream, "stop", usage_stats
            )
    except (QuotaExceededError, QuotaExceededRetry):
        raise
    except ClientDisconnectedError:
        if data_receiving and not completion_event.is_set():
            completion_event.set()
    except asyncio.CancelledError:
        if not completion_event.is_set():
            completion_event.set()
        raise
    except Exception as e:
        logger.error(
            f"[{req_id}] Error in Playwright stream generator: {e}", exc_info=True
        )
        try:
            yield generate_sse_chunk(
                f"\n\n[Error: {str(e)}]", req_id, model_name_for_stream
            )
            yield generate_sse_stop_chunk(req_id, model_name_for_stream)
        except Exception:
            pass
    finally:
        if not completion_event.is_set():
            completion_event.set()
