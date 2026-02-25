# API Usage Guide

This project exposes OpenAI-compatible endpoints through FastAPI.

## Base URL

Default local base URL:

```text
http://127.0.0.1:2048/v1
```

You can confirm runtime URLs via:

- `GET /api/info`

## Core Endpoints

### 1) Health

- `GET /health`
- Returns `200` when core components are ready
- Returns `503` when initializing or unavailable

### 2) Model list

- `GET /v1/models`
- Returns available models (fallback model if list is temporarily unavailable)

### 3) Chat completions

- `POST /v1/chat/completions`
- OpenAI-style request body (`model`, `messages`, `stream`, etc.)

Example:

```bash
curl -X POST http://127.0.0.1:2048/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-2.5-pro",
    "messages": [{"role":"user","content":"Hello"}],
    "stream": false
  }'
```

Streaming example:

```bash
curl -X POST http://127.0.0.1:2048/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-2.5-pro",
    "messages": [{"role":"user","content":"Tell me a short story"}],
    "stream": true
  }' --no-buffer
```

## Function Calling

The server supports tool calling (`tools` / `tool_calls`) with configurable behavior:

- `FUNCTION_CALLING_MODE=auto` (recommended)
- `FUNCTION_CALLING_MODE=native`
- `FUNCTION_CALLING_MODE=emulated`

`auto` attempts native behavior first, then falls back when needed.

## Queue and cancellation endpoints

- `GET /v1/queue`: returns queue length and queued request metadata
- `POST /v1/cancel/{req_id}`: cancels queued request by request id

## Authentication

If `auth_profiles/key.txt` contains keys, protected endpoints require:

- `Authorization: Bearer <token>`
- or `X-API-Key: <token>`

If no keys are configured, requests are accepted without key validation.
