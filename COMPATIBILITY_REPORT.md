# Browser compatibility audit — 2026-09-08

This fork is **experimental, not production-ready**. The application segmentation
prompt and strict parser were preserved. No customer history or application-credit
write was made, and no API-key Gemini fallback, billing selection, account rotation,
or external helper was enabled. Provider billing was not independently audited.

## Verified locally

- Python 3.12, Playwright 1.62.0, Camoufox 0.4.11 with browser 152.0.4-beta.30 on macOS.
- Both launchers select the shared public-API bridge; a real-browser local fixture
  covers settings opening/closing, native file selection, exact prompt filling, and Run.
- Human Google login, owner-approved 0600 authentication save, and a subsequent
  successful restart without another login. Authentication and diagnostics are ignored
  by Git; no other browser's authentication was imported.
- Actual model selection/readback: `gemini-3.8-flash`; Low thinking applied, Google
  Search/other tools off, no implicit `User:` stop sequence in the final live replay.
- An explicit unsupported `temperature=0` request receives HTTP 422 before generation.
  The [3.8 migration contract](https://ai.google.dev/gemini-api/docs/latest-model)
  removes temperature/top_p/top_k; model-default and old temperature=0 trials are not
  sampling-identical experiments.

## Live findings

1. The original closed-settings-panel failure was initialization, not failed login.
   Opening the panel and checking the rendered model fixes this path.
2. New chat restores UI defaults. A stale parameter cache skipped Low on the next
   request; per-request invalidation and readback now prevent silent misconfiguration.
3. The current Run button lacks the old submit attributes. The responsive right
   panel can also cover Run; the final patch closes it after settings verification.
   That last panel-closure change is fixture-tested, not a successful live generation.
   The follow-up below tests panel closure live and supersedes that validation status.
4. The old broad pre-click overlay helpers could stall before Run. They are no longer
   used by the main controller; arbitrary consent buttons are not auto-accepted.
5. Most importantly, the final live two-image replay reached AI Studio generation but
   both calls returned **permission denied**, with an internal-error model turn.
   They failed in 19.074 s and 15.799 s end to end (including browser setup/cleanup).
   These are failure latencies, not generation-speed measurements. Saved screenshots
   show the provider toast; no segmentation text reached the application parser.

The permission cause (account/model entitlement, provider policy, session, etc.) is
not established by the toast. Do not assume that it requires a paid key or that a
new account would fix it. A person should confirm permitted generation directly in
AI Studio. Do not retry access-denied requests indefinitely or circumvent the denial.

An earlier trial timed out at 180 s before Run and its queued second request was
interrupted during the corrective restart; it is not counted as two provider failures.
Earlier Antigravity replays of the same two inputs passed the unchanged parser, but
two samples do not establish stability. The planned fixed 30-image comparison,
crop quality, response-extraction fidelity, Linux, and throughput remain unverified.

## Follow-up: settings panel / normal-button hypothesis

At 06:32 KST on 2026-09-08, the user requested a controlled check of whether sending
while the settings panel was open caused the permission denial. The same authenticated
proxy session, exact first image, prompt hash, model, Low thinking, and model-default
sampling policy were retained. No identity/security/anti-detection changes were made.

- 06:32:56.153: settings panel confirmed hidden.
- 06:32:56.201: native file selection completed.
- 06:32:57.324: normal Playwright Run click completed with hit-testing; no force,
  DOM click, keyboard fallback, or automatic resubmission.
- 06:32:57.966: permission-denied UI confirmed and reported as an upstream error.
- End-to-end failure: 10.916 s; no segmentation text reached the parser.

Thus the open-panel submission is **not the sole explanation**. The trial does not
establish or exclude automation detection, session issues, or account/model access.
A same-window, human-clicked text-only control was prepared but not submitted by
the agent. Its result is pending; this control is not a segmentation A/B sample.
Do not proceed to 30-image requests until permitted generation is established.

## Repeatable checks

Final local unit run: **2,345 passed, 9 skipped, 68 integration-marked tests excluded**
in 65.06 s, with 59 warnings (including inherited unawaited-coroutine/deprecation
warnings). Ruff and targeted Pyright checks passed. This is not full integration
coverage; the real-browser no-Google fixture passed separately.

```sh
uv sync --locked --check
uv run ruff check .
uv run pytest --no-cov -m 'not integration'
uv run python scripts/browser_runtime_smoke.py
```

The app-side diagnostic transport and unchanged parser also passed 27 tests in
their separate repository. Do not confuse unit/fixture success with live Google QA.
Consult GETTING_STARTED.md and AGENTS.md before continuing; preserve all failure
evidence privately and never commit auth files, customer images, or full snapshots.
