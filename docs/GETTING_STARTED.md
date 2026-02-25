# Getting Started (Latest)

This guide is the fastest reliable path to run AI Studio Proxy API EN.

## 1) Prerequisites

- Python `>=3.9,<4.0` (3.10 or 3.11 recommended)
- [Poetry](https://python-poetry.org/)
- Stable network access to Google AI Studio
- At least 2 GB available memory (4 GB+ recommended)

## 2) Install

```bash
git clone https://github.com/MasuRii/AIstudioProxyAPI-EN.git
cd AIstudioProxyAPI-EN
poetry install
poetry run camoufox fetch
```

## 3) Configure

```bash
cp .env.example .env
```

Then update `.env` if needed:

- `PORT` (default `2048`)
- `STREAM_PORT` (default `3120`, set `0` to disable stream proxy)
- `UNIFIED_PROXY_CONFIG` (if you need a proxy)

## 4) First login and auth profile creation

Run interactive mode once and save auth state:

```bash
poetry run python launch_camoufox.py --debug --auto-save-auth --save-auth-as my_account
```

After successful login, auth state will be saved under `auth_profiles/saved/`.

## 5) Headless daily run

```bash
poetry run python launch_camoufox.py --headless --active-auth-json auth_profiles/saved/my_account.json
```

## 6) Verify service

```bash
curl http://127.0.0.1:2048/health
curl http://127.0.0.1:2048/v1/models
```

## 7) Optional: Build frontend once

The backend serves files from `static/frontend/dist`. Build once before using `/`:

```bash
cd static/frontend
npm install
npm run build
cd ../..
```

Then open `http://127.0.0.1:2048/`.

## 8) GUI launchers

```bash
# Simple Tk launcher
poetry run python simple_launcher.py

# CustomTkinter launcher module
poetry run python -m gui
```
