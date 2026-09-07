# Maintained browser-compatibility fork

This fork updates AI Studio browser automation for local Questi transport experiments.
It does not replace the application's problem-generation pipeline or loosen its
segmentation parser. A successful HTTP response is not evidence of correct model,
sampling settings, segmentation, or zero billing.

## Reproducible setup

Python 3.10+ is required by the pinned Playwright 1.62 / Camoufox 0.5.6 packages;
Python 3.12 is the verified local runtime. Stop the service before synchronizing
its Python environment, or use `uv run --isolated` for a separate test environment.

```sh
uv sync --locked --python 3.12
uv run python scripts/install_camoufox.py
uv run python scripts/browser_runtime_smoke.py
```

The smoke check starts a real browser using the public Playwright Node API, exercises
a local collapsed-panel fixture, and stops its own process group. It does not contact
Google, request authentication, or invoke a model. macOS was tested locally; Linux
still needs its browser/system dependencies and a live verification on that host.

The installer selects the verified official `152.0.4-beta.30` browser for the actual
host OS/architecture and requires its published SHA-256 digest. It installs to the
package's versioned subdirectory without deleting the legacy browser files; it also
updates the package-manager's active-version metadata. It does not touch login
profiles. Avoid the upstream 0.5.6 `camoufox fetch` command during migration: it can
delete a nonempty old cache. Launchers fail early on that unmigrated state and point
to the safe installer instead. Keep legacy files while an old process uses them.
Additional browser copies consume disk space; this workflow does not remove them.

Camoufox 0.5.6 now includes the public Playwright server implementation, so this
fork no longer substitutes its own Node bridge. The official newline-frame / open
stdin lifecycle is covered by a real Node regression test; waiting for EOF before
launch would hang the updated Python server. The browser fixture prints both the
Python package version and actual browser version to prevent confusing them.

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

## Provider access and diagnostics

An actual GenerateContent HTTP 403 or the exact permission-denied toast pauses
automatic submissions. `/v1/chat/completions` then returns 403 with
`detail.code=aistudio_generation_permission_denied` and `detail.retryable=false`.
New requests are rejected before queuing, and already queued requests are checked
again before submission. Quota exhaustion (429) is not classified as this denial.

`/health` includes `details.generationAccess` (`unknown`, `accepted`, or `denied`),
its observation time and the HTTP status when available. It returns 503 when denied,
even if `workerRunning` and browser-ready flags remain true. Treat this as lack of
generation readiness, **not** a liveness check that triggers repeated restarts.
The latch is process-local, not a persistent account-access database; restarting is
not an access fix. Human/provider access review is required. A naturally observed
GenerateContent 200 clears the latch; that status is not proof of valid model output
or permission for future automated requests. No automatic recovery probe is sent.

For a bounded local investigation, add `SUBMISSION_DIAGNOSTICS=true` to the launch
environment. It defaults to false. `GET /api/diagnostics/submission` is available only
to a loopback client while enabled. It reads editor length/focus/readiness, Run-button
hit-testing and sanitized RPC method/status metadata, without sending a prompt.
Failed generation responses can additionally log standard error enums or coarse
non-JSON format indicators; no raw response text, request body, headers, prompt text
or credentials are emitted by this diagnostic. Inherited screenshots/network logs
are separate private artifacts and must not be published. Do not enable this on an
externally exposed or reverse-proxied deployment.

These changes make denial observable and stop futile retries. They **do not fix**
the current human-input versus automated-input discrepancy; see the audit report.

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
- Both launchers use Camoufox 0.5.6's official public-API server with the shared
  non-destructive cache guard; the obsolete repository-owned bridge was removed.
- Current file uploads can use the actual native file input instead of translated
  menu labels. Both current and legacy stop-sequence field labels are recognized.
- The current Run button is identified without requiring removed `type="submit"`
  or `aria-label="Run"` attributes; the real-browser fixture covers the new markup.
  After settings verification, the responsive settings panel is closed so it does
  not intercept Run clicks. Prompt filling and file selection have bounded waits;
  submission does not accept arbitrary consent dialogs or remove application DOM.
  The main submission path uses one normal Run click only. A disabled/covered button
  or failed upload fails the request: there is no hotkey or automatic resubmit fallback.
  The prepared prompt is read back after filling and again after attachments, just
  before Run. A mismatch fails before submission instead of silently rewriting it.
  This guard does not resolve the observed permission denial; physical typing and
  automated input still differ in live controls (see COMPATIBILITY_REPORT.md).
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
Even a single user message is currently wrapped as `User:\n...\n` and stripped of
outer whitespace by the inherited formatter. Editor readback verifies that prepared
text, not byte-for-byte preservation of incoming message text. This boundary must
be addressed explicitly before claiming application-pipeline transport equivalence.
