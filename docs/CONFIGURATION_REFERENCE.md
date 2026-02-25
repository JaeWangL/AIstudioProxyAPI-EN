# Configuration Reference (Important Settings)

All runtime behavior is controlled via `.env` (copy from `.env.example`).

## Server and networking

| Variable | Default | Purpose |
|---|---:|---|
| `PORT` | `2048` | FastAPI server port |
| `STREAM_PORT` | `3120` | Streaming proxy port (`0` disables stream proxy) |
| `UNIFIED_PROXY_CONFIG` | empty | Unified proxy for HTTP/HTTPS/internal browser |
| `HTTP_PROXY` / `HTTPS_PROXY` | empty | Legacy proxy fallback |

## Launch behavior

| Variable | Default | Purpose |
|---|---:|---|
| `LAUNCH_MODE` | `normal` | Launch strategy |
| `DIRECT_LAUNCH` | `false` | Bypass launcher menu and start directly |
| `CAMOUFOX_WS_ENDPOINT` | empty | Connect to external browser websocket if used |

## Authentication and session lifecycle

| Variable | Default | Purpose |
|---|---:|---|
| `AUTO_SAVE_AUTH` | `false` | Auto-save auth state after login |
| `AUTH_SAVE_TIMEOUT` | `30` | Save prompt timeout (seconds) |
| `AUTO_ROTATE_AUTH_PROFILE` | `true` | Rotate auth profile on issues/quota |
| `AUTO_AUTH_ROTATION_ON_STARTUP` | `false` | Auto-select fallback profile at startup |

## Quota and resilience

| Variable | Default | Purpose |
|---|---:|---|
| `QUOTA_SOFT_LIMIT` | `850000` | Rotation pending threshold |
| `QUOTA_HARD_LIMIT` | `950000` | Immediate rotation/stop threshold |
| `COOKIE_REFRESH_ENABLED` | `true` | Periodic cookie refresh |
| `COOKIE_REFRESH_INTERVAL_SECONDS` | `1800` | Periodic refresh interval |

## Function calling

| Variable | Default | Purpose |
|---|---:|---|
| `FUNCTION_CALLING_MODE` | `auto` | `auto`, `native`, or `emulated` |
| `FUNCTION_CALLING_NATIVE_FALLBACK` | `true` | Fallback when native mode fails |
| `FUNCTION_CALLING_UI_TIMEOUT` | `10000` | UI operation timeout (ms) |
| `FUNCTION_CALLING_NATIVE_RETRY_COUNT` | `3` | Native-mode retry count |
| `FUNCTION_CALLING_THOUGHT_SIGNATURE` | `true` | Gemini 3.x compatibility option |

## Logging

| Variable | Default | Purpose |
|---|---:|---|
| `SERVER_LOG_LEVEL` | `INFO` | Main server log level |
| `DEBUG_LOGS_ENABLED` | `false` | Enable debug logs |
| `TRACE_LOGS_ENABLED` | `false` | Enable trace-level logs |
| `JSON_LOGS` | `false` | Structured JSON logging |

## Recommended baseline for first run

```env
PORT=2048
STREAM_PORT=3120
SERVER_LOG_LEVEL=INFO
AUTO_SAVE_AUTH=true
AUTO_ROTATE_AUTH_PROFILE=true
FUNCTION_CALLING_MODE=auto
```

For full option coverage, read `.env.example`.
