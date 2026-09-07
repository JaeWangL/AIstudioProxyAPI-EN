# Maintained browser-compatibility fork

This fork updates AI Studio browser automation for local Questi transport experiments.
It does not replace the application's problem-generation pipeline or loosen its
segmentation parser. A successful HTTP response is not evidence of correct model,
sampling settings, segmentation, or zero billing.

## Reproducible setup

Python 3.10+ is required by Playwright 1.62; Python 3.12 is the verified local runtime.

```sh
uv sync --locked --python 3.12
uv run python -m camoufox fetch
uv run python scripts/browser_runtime_smoke.py
```

The smoke check starts a real browser using the public Playwright Node API, exercises
a local collapsed-panel fixture, and stops its own process group. It does not contact
Google, request authentication, or invoke a model. macOS was tested locally; Linux
still needs its browser/system dependencies and a live verification on that host.

Poetry 2.3 remains supported for upstream CI. When changing runtime dependencies,
update both dependency tables in `pyproject.toml`, regenerate `uv.lock` and
`poetry.lock`, and run the checks below. Do not edit installed site-packages or pin
an old Playwright solely to preserve private `lib/browserServerImpl.js` imports.

## Manual login and local-only service

```sh
AI_STUDIO_BIND_HOST=127.0.0.1 CAMOUFOX_BIND_HOST=127.0.0.1 \
AUTO_SAVE_AUTH=false AUTO_ROTATE_AUTH_PROFILE=false \
COOKIE_REFRESH_ENABLED=false COOKIE_REFRESH_ON_REQUEST_ENABLED=false \
COOKIE_REFRESH_ON_SHUTDOWN=false ENABLE_SCRIPT_INJECTION=false \
NETWORK_INTERCEPTION_ENABLED=false \
DEFAULT_STOP_SEQUENCES='[]' \
uv run python launch_camoufox.py --debug --server-port 2048 \
  --camoufox-debug-port 9222 --stream-port 0 --helper '' \
  --internal-camoufox-proxy '' --auto-auth-rotation-on-startup false
```

A **person** completes Google login in the newly opened browser, then confirms it in
the terminal. Do not import another browser's cookies, export credentials, select a
paid API key, enable a billing project, or rotate accounts to evade quota limits.
Check that no external helper/proxy or saved authentication profile is selected by
your local `.env`; the audit runs without those integrations.

With the account owner's permission, add `--save-auth-as local-qa` for the initial
human login. This saves only that proxy context to `auth_profiles/saved/local-qa.json`
(directory mode 0700, file mode 0600, Git-ignored). For subsequent starts, replace
that option with `--active-auth-json auth_profiles/saved/local-qa.json`. Never log
the file contents or copy authentication from a different browser. A revoked or
expired session still requires human login; rotation remains disabled.

The API bind remains upstream-compatible (`0.0.0.0`) unless `AI_STUDIO_BIND_HOST` is
set, so keep the loopback setting above. The browser control port defaults to
loopback. Do not expose either service to an untrusted network.

After readiness, read `/health` and `/v1/models`; use an exact advertised model ID.
For segmentation experiments use `gemini-3.8-flash` only if advertised, with explicit
`reasoning_effort: low`. Omit `temperature`, `top_p`, and `top_k`: the current 3.8 UI
does not offer these controls and Google's [migration guide](https://ai.google.dev/gemini-api/docs/latest-model)
requires removing them. Explicit unsupported overrides are rejected with 422, not
silently ignored. `minimal`/numeric thinking budgets are also rejected for 3.8.
Never silently substitute another model. Omitted thinking effort defaults to medium.

## What changed

- The current Playground can remove a closed run-settings panel from the DOM.
  Readiness now opens its visible toggle and reads the actual rendered model.
- A model already written to localStorage is no longer accepted as a verified switch.
- Explicit numeric request settings are read back; a failed temperature update must
  stop processing before prompt submission. Gemini 3 thinking levels are also checked.
- Startup errors identify input vs. model-settings failure. Private startup metadata
  is saved before the local page is cleaned up. Optional screenshots require
  `BROWSER_INIT_SCREENSHOTS=true`; never commit diagnostics or authentication files.
- Initialization cancellation no longer leaves blocking executor threads behind.
- Profile-selection tests use isolated temporary directories, not the developer's
  saved authentication files; launcher-default tests no longer depend on module reload order.
- Both launchers use a repository-owned public-API bridge for Camoufox/Playwright.
- Current file uploads can use the actual native file input instead of translated
  menu labels. Both current and legacy stop-sequence field labels are recognized.
- The current Run button is identified without requiring removed `type="submit"`
  or `aria-label="Run"` attributes; the real-browser fixture covers the new markup.
  After settings verification, the responsive settings panel is closed so it does
  not intercept Run clicks. Prompt filling and file selection have bounded waits;
  submission does not accept arbitrary consent dialogs or remove application DOM.
  The main submission path uses one normal Run click only. A disabled/covered button
  or failed upload fails the request: there is no hotkey or automatic resubmit fallback.
- Parameter caches are invalidated before each request: New chat may restore UI
  defaults without changing the selected model. Cached thinking levels are not proof.
- An explicit internal-generation error in the model turn is reported as an upstream
  error, not a segmentation-format failure; response-location errors save diagnostics.
  The observed permission-denied toast is surfaced separately for human review;
  the proxy does not change billing, credentials, or accounts in response.

## Verification and maintenance

```sh
uv sync --locked
uv run ruff check .
uv run pytest -m 'not integration'
uv run python scripts/browser_runtime_smoke.py
```

For live validation, first replay the same failed image bytes with the unchanged
application prompt/parser; save input and response hashes, requested/observed model,
settings, latency, and failure stage. An original temperature=0 replay and a 3.8
model-default replay are different experiments; never label them sampling-identical.
Then expand to a fixed 30-image sample. Distinguish
UI/transport failure, parser rejection, and visual crop quality. Do not create customer
histories or deduct application credits during a transport-only comparison.

Upstream for this fork is `MasuRii/AIstudioProxyAPI-EN` (base `c764934`). Fetch and review
upstream changes on a branch; run the checks and live smoke before merging. Do not
overwrite local compatibility patches or auto-upgrade dependencies without tests.
The inherited upstream-sync workflow is not proof that this fork has been validated
against today's Google UI; it must not silently merge UI changes or conflicts.

Known boundaries: the upstream uses one shared browser/processing lock (serial
inference), flattens system instructions into prompt text, and is not a full Gemini
SDK replacement. JSON-schema/tool/PDF/response-extraction equivalence requires
separate validation. Quota exhaustion should be surfaced or waited out, not hidden.
