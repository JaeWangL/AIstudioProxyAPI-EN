import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from api_utils.routers.submission_diagnostics import submission_diagnostics
from browser_utils.submission_diagnostics import (
    error_summary,
    log_generation_failure,
    log_submission_state,
    read_submission_state,
    rpc_summary,
)


def test_error_summary_never_returns_message_or_metadata():
    payload = {
        "error": {
            "code": 403,
            "status": "PERMISSION_DENIED",
            "message": "SECRET",
            "details": [
                {
                    "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                    "reason": "ACCESS_DENIED",
                    "metadata": {"token": "SECRET"},
                }
            ],
        }
    }
    assert error_summary(payload) == {
        "structured_error": True,
        "code": 403,
        "status": "PERMISSION_DENIED",
        "reasons": ["ACCESS_DENIED"],
    }
    assert error_summary(["SECRET"]) == {"structured_error": False}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,url,read",
    [
        (
            403,
            "https://alkalimakersuite-pa.clients6.google.com/$rpc/Service/GenerateContent?key=SECRET",
            True,
        ),
        (
            200,
            "https://alkalimakersuite-pa.clients6.google.com/$rpc/Service/GenerateContent",
            False,
        ),
        (403, "https://accounts.google.com/token", False),
    ],
)
async def test_error_body_read_is_only_for_generation_failure(
    monkeypatch, status, url, read
):
    monkeypatch.setenv("SUBMISSION_DIAGNOSTICS", "true")
    response = MagicMock(status=status, url=url)
    response.text = AsyncMock(
        return_value=')]}\'\n{"error":{"code":403,"status":"PERMISSION_DENIED","message":"SECRET"}}'
    )
    logger = MagicMock()
    await log_generation_failure(response, logger)
    assert response.text.await_count == int(read)
    assert "SECRET" not in str(logger.mock_calls)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body,expected",
    [
        (
            "<!DOCTYPE html><html>unusual traffic SECRET</html>",
            '"unusual_traffic_notice": true',
        ),
        ("non-json SECRET", '"format": "other"'),
        ("SECRET" * 12000, "exceeds diagnostic bound"),
    ],
)
async def test_non_json_failure_is_bounded_and_redacted(monkeypatch, body, expected):
    monkeypatch.setenv("SUBMISSION_DIAGNOSTICS", "true")
    response = MagicMock(
        status=403,
        url="https://alkalimakersuite-pa.clients6.google.com/$rpc/Service/GenerateContent",
    )
    response.text = AsyncMock(return_value=body)
    logger = MagicMock()
    await log_generation_failure(response, logger)
    assert expected in str(logger.mock_calls)
    assert "SECRET" not in str(logger.mock_calls)


def test_rpc_summary_drops_sensitive_urls_and_all_payloads():
    responses = [
        {
            "url": "https://alkalimakersuite-pa.clients6.google.com/$rpc/Service/GenerateContent?key=SECRET",
            "status": 403,
            "body": "SECRET",
        },
        {"url": "https://accounts.google.com/token?secret=SECRET", "status": 200},
        {
            "url": "https://alkalimakersuite-pa.clients6.google.com/$rpc/Service/secret-123",
            "status": 200,
        },
    ]
    assert rpc_summary({"responses": responses}) == [
        {"rpc": "GenerateContent", "status": 403}
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "flag,host", [("false", "127.0.0.1"), ("true", "192.0.2.1"), ("true", None)]
)
async def test_diagnostics_endpoint_off_or_nonlocal_is_hidden(monkeypatch, flag, host):
    monkeypatch.setenv("SUBMISSION_DIAGNOSTICS", flag)
    request = Request({"type": "http", "client": (host, 1234) if host else None})
    with pytest.raises(HTTPException) as exc:
        await submission_diagnostics(request)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_disabled_diagnostics_never_evaluates_page(monkeypatch):
    monkeypatch.delenv("SUBMISSION_DIAGNOSTICS", raising=False)
    page = MagicMock()
    await log_submission_state(page, MagicMock(), "test", "before_run")
    page.evaluate.assert_not_called()


@pytest.mark.asyncio
async def test_diagnostics_never_inspect_login_origin():
    page = MagicMock(url="https://accounts.google.com/login")
    with pytest.raises(RuntimeError):
        await read_submission_state(page, {})
    page.evaluate.assert_not_called()


@pytest.mark.asyncio
async def test_read_only_evaluation_has_no_sensitive_state():
    page = MagicMock(url="https://aistudio.google.com/prompts/new_chat")
    page.evaluate = AsyncMock(return_value={"has_focus": False})
    assert await read_submission_state(page, {}) == {
        "has_focus": False,
        "rpc_responses": [],
    }
    expression = page.evaluate.call_args.args[0]
    for forbidden in (
        "localStorage",
        "cookie",
        "fetch(",
        "dispatchEvent",
        ".click(",
        "userAgent",
    ):
        assert forbidden not in expression


@pytest.mark.asyncio
async def test_diagnostic_failure_does_not_trigger_actions(monkeypatch):
    monkeypatch.setenv("SUBMISSION_DIAGNOSTICS", "true")
    page = MagicMock()
    with patch(
        "browser_utils.submission_diagnostics.read_submission_state",
        AsyncMock(side_effect=RuntimeError("PRIVATE")),
    ):
        logger = MagicMock()
        await log_submission_state(page, logger, "test", "before_run")
        assert "PRIVATE" not in str(logger.mock_calls)
    page.assert_not_called()


@pytest.mark.asyncio
async def test_diagnostic_cancellation_propagates(monkeypatch):
    monkeypatch.setenv("SUBMISSION_DIAGNOSTICS", "true")
    with patch(
        "browser_utils.submission_diagnostics.read_submission_state",
        AsyncMock(side_effect=asyncio.CancelledError),
    ):
        with pytest.raises(asyncio.CancelledError):
            await log_submission_state(MagicMock(), MagicMock(), "test", "before_run")
