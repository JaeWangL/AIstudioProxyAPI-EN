<h1 align="center">AI Studio Proxy API EN</h1>

<p align="center">
  OpenAI-compatible proxy for Google AI Studio powered by <strong>FastAPI</strong>, <strong>Playwright</strong>, and <strong>Camoufox</strong>.
</p>

<p align="center">
  <a href="https://github.com/MasuRii/AIstudioProxyAPI-EN/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-AGPLv3-red.svg" alt="License: AGPLv3"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.9%2B-blue.svg" alt="Python 3.9+"></a>
  <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-0.115.x-009688.svg" alt="FastAPI"></a>
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-6f42c1.svg" alt="Platform">
</p>

![alt text](assets/img/aistudio_illustration.png)

---

## Overview

AI Studio Proxy API EN converts Google AI Studio web interactions into OpenAI-style endpoints such as:

- `POST /v1/chat/completions`
- `GET /v1/models`
- `GET /health`

It is suitable for users who want OpenAI-compatible clients to work with AI Studio through browser automation.

---

## Acknowledgements

This project exists thanks to the work and support of many contributors and communities:

- **Project initiation and main development**: @CJackHwang ([GitHub](https://github.com/CJackHwang))
- **Feature enhancement and page operation optimization ideas**: @ayuayue ([GitHub](https://github.com/ayuayue))
- **Real-time streaming functionality optimization and improvement**: @luispater ([GitHub](https://github.com/luispater))
- **Large-scale main file refactoring contribution**: @yattin (Holt) ([GitHub](https://github.com/yattin))
- **High-quality project maintenance in later stages**: @Louie ([GitHub](https://github.com/NikkeTryHard))
- **English version maintainer**: @MasuRii ([GitHub](https://github.com/MasuRii))
- **Community support and inspiration**: [Linux.do Community](https://linux.do/)

Thank you to everyone who contributed through issues, reviews, feedback, and code improvements.

---

## System Requirements

- **Python**: `>=3.9,<4.0` (3.10+ recommended)
- **Package manager**: [Poetry](https://python-poetry.org/)
- **OS**: Windows / macOS / Linux
- **Memory**: 2 GB minimum (4 GB+ recommended)
- **Network**: Stable access to Google AI Studio (proxy supported)

---

## Key Features

- OpenAI-compatible API routes
- Native + emulated function-calling support (`tools` / `tool_calls`)
- Streaming proxy support
- Model switching via request payload
- Optional API-key authentication
- Auth profile save/rotation support
- Built-in web UI backend routes (`/`, `/assets/*`, `/api/info`)
- GUI launcher options (`simple_launcher.py` and `python -m gui`)

---

## Quick Start

### 1) Clone and install

```bash
git clone https://github.com/MasuRii/AIstudioProxyAPI-EN.git
cd AIstudioProxyAPI-EN
poetry install
poetry run camoufox fetch
```

### 2) Configure environment

```bash
cp .env.example .env
```

Edit `.env` as needed (ports, proxy, auth behavior, logging, etc.).

### 3) First authentication (interactive)

```bash
poetry run python launch_camoufox.py --debug --auto-save-auth --save-auth-as my_account
```

### 4) Headless run (using saved auth)

```bash
poetry run python launch_camoufox.py --headless --active-auth-json auth_profiles/saved/my_account.json
```

---

## API Smoke Test

```bash
# Health check
curl http://127.0.0.1:2048/health

# Model list
curl http://127.0.0.1:2048/v1/models

# Chat completion (non-stream)
curl -X POST http://127.0.0.1:2048/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gemini-2.5-pro","messages":[{"role":"user","content":"Hello"}]}'
```

---

## Web UI (Frontend Build)

The backend serves frontend files from `static/frontend/dist`. If they are not built yet, `/` will return an error.

Build once:

```bash
cd static/frontend
npm install
npm run build
cd ../..
```

Then open:

- `http://127.0.0.1:2048/`

---

## Launchers

```bash
# Simple Tk launcher
poetry run python simple_launcher.py

# CustomTkinter launcher module
poetry run python -m gui
```

---

## One-Click Install Scripts

```bash
# macOS/Linux
curl -sSL https://raw.githubusercontent.com/MasuRii/AIstudioProxyAPI-EN/main/scripts/install.sh | bash

# Windows PowerShell
iwr -useb https://raw.githubusercontent.com/MasuRii/AIstudioProxyAPI-EN/main/scripts/install.ps1 | iex
```

---

## Documentation

- [Getting Started](docs/GETTING_STARTED.md)
- [API Usage Guide](docs/API_USAGE.md)
- [Authentication Profiles Guide](docs/AUTH_PROFILES.md)
- [Configuration Reference](docs/CONFIGURATION_REFERENCE.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Docker Quick Start](docker/README.md)
- [Docker Deployment Details](docker/README-Docker.md)

---

## Project Structure

- `launch_camoufox.py` — main launcher/orchestration
- `server.py` — FastAPI app entry
- `api_utils/` — routers, app lifecycle, request handling
- `browser_utils/` — Playwright/browser automation logic
- `stream/` — streaming proxy components
- `config/` — environment and global configuration
- `docs/` — user documentation and operational guides
- `auth_profiles/` — saved/active auth files
- `static/frontend/` — React frontend source

---

## Development Checks

```bash
poetry run ruff check .
poetry run pyright
poetry run pytest
```

---

## License

This project is licensed under [AGPLv3](LICENSE).
