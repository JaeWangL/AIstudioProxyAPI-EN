# Troubleshooting

## 1) `/health` returns 503

Possible causes:

- Browser session is not initialized yet
- Auth profile is missing/expired
- Stream proxy startup failed

What to do:

1. Start with visible mode to inspect login state:
   ```bash
   poetry run python launch_camoufox.py --debug
   ```
2. Confirm auth file exists and is valid.
3. Check logs for startup failures.

## 2) Cannot access web UI at `/`

The backend serves frontend files from `static/frontend/dist`.
If not built, `/` returns a frontend build error.

Fix:

```bash
cd static/frontend
npm install
npm run build
cd ../..
```

## 3) Requests fail due to quota or unstable sessions

Use auth rotation settings in `.env`:

- `AUTO_ROTATE_AUTH_PROFILE=true`
- Tune `QUOTA_SOFT_LIMIT` and `QUOTA_HARD_LIMIT`
- Keep multiple valid profiles in `auth_profiles/saved/`

## 4) API key errors (`401 invalid_api_key`)

- Ensure key is present in `auth_profiles/key.txt`
- Send either:
  - `Authorization: Bearer <token>`
  - `X-API-Key: <token>`

If `key.txt` is empty, key checks are disabled.

## 5) Port already in use

Change ports in `.env` and restart:

```env
PORT=2048
STREAM_PORT=3120
```

Or stop the process currently using those ports.

## 6) Proxy/network issues

Set `UNIFIED_PROXY_CONFIG` in `.env` when Google AI Studio requires proxy access:

```env
UNIFIED_PROXY_CONFIG=http://127.0.0.1:7890
```

## 7) Headless mode starts but no response

Common root causes:

- Invalid auth profile
- Browser endpoint problems
- Upstream UI changes affecting automation selectors

Recommended recovery:

1. Re-authenticate in debug mode
2. Save a fresh auth profile
3. Retry headless with explicit `--active-auth-json`
