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
A same-window, human-clicked text-only control was prepared. Its result and the
subsequent input-method controls are recorded below; these are not segmentation
A/B samples. Do not proceed to 30-image requests until proxy generation works.

## Follow-up: pasted input versus typed input

At 06:38–06:40 KST, inspection after the user's success report showed:

- The prepared `Reply with exactly OK.` turn had an internal error.
- Two subsequent user-entered Korean greetings received model replies; the latest
  was a normal Korean greeting. Basic generation is therefore not universally
  unavailable in this session, but prompt content and conversation position differed.
- A fresh chat's settings were read back as `gemini-3.8-flash`, Low, tools off,
  with no API key selected. The settings panel was closed before all controls.

The user supplied this [copy/paste bug report](https://discuss.ai.google.dev/t/widespread-permission-denied-error-in-ai-studio-is-actually-caused-by-copy-paste-100-reproducible/179348).
It is a forum user's reproduction report; the visible staff reply asks for details,
not a confirmed explanation of a backend security mechanism.

Three bounded native-UI controls, each in a fresh chat and using one normal Run
click, all produced the visible permission-denied toast and internal-error turn:

1. Paste the prompt prefix, then append the final period using the text-entry tool.
2. Paste the complete prompt, press Space, then Backspace (exact original text).
3. Paste the complete prompt, press Space and leave the trailing space, matching
   the reported workaround. The extra space was verified before submission.

These controls do not prove that native automation, Playwright filling, and physical
typing dispatch identical events. They also do not establish account-wide denial,
automation detection, or the root cause of this failure. The advertised workaround
did not resolve this local reproduction, so no speculative input workaround was
added to the controller and no segmentation prompt was changed. A physical-typing
control with the same English prompt in a fresh chat remains needed to separate
input method from prompt/conversation effects. Automatic generation attempts stopped.

No application histories/credits, paid API fallback, billing choices, authentication,
browser identity, security settings, or account-rotation settings were changed.

## Follow-up: physical typing succeeds, automated typing does not

At 06:46 KST the user physically typed `reply with exactly OK.` into the prepared
fresh chat and received `OK.`; both turns were verified in the UI. The initial `r`
was lowercase, unlike the earlier prepared sentence. This strengthens the input-path
hypothesis but does not by itself establish the underlying editor/security mechanism.

A candidate replaced bulk prompt filling with Playwright's public
[`press_sequentially`](https://playwright.dev/python/docs/api/class-locator#locator-press-sequentially),
without inserted sentinel characters or timing/identity/security changes. Exact
editor readback and one normal Run click were enforced. After restarting with the
same approved proxy authentication:

- A text-only HTTP request for that lowercase sentence, 3.8 Flash / Low / tools off,
  failed with provider permission denied in **9.460 s** (06:49 KST).
- Log inspection exposed an important comparison boundary: the upstream formatter
  actually entered `User:\nreply with exactly OK.\n` (29 characters), not the literal
  22-character sentence. It also strips message whitespace. The original application
  prompt builder/parser was unchanged, but that alone does not prove wire-prompt
  equivalence. The prior input hashes describe adapter inputs, not the final UI text.
- To separate that formatting difference, a fresh native-UI control verified 3.8
  Flash / Low, closed the panel, and entered the literal lowercase sentence entirely
  through individual key presses (no paste or text-entry helper). The value was
  verified before one normal Run click. It also returned permission denied at 06:50.

Thus neither sequential Playwright typing nor native automated keys reproduced the
physical-typing success. These are bounded diagnostics, not repeated access-denial
retries or a proven workaround. An additional controller-only probe could not attach
to the existing context through a second public Playwright client and stopped before
submission; it is not counted as a generation failure.

The ineffective sequential-input candidate was reverted. The final code retains
only exact readback guards after input and immediately before Run, with mismatch,
cancellation and single-submission tests. The real-browser fixture also covers
multiline Korean, LaTeX, emoji, combining characters, tabs and trailing whitespace.
No copy/paste fix or successful automated generation is claimed. Account-wide denial
is contradicted by the physical control, but editor state, automated-input handling
and session/provider behavior are not yet isolated. No more automatic generation
or 30-image comparison was started, and no business DB/credit/API-key writes occurred.

## Follow-up: user reports manual copy/paste also succeeds

After the physical-typing controls, the user reported that their own copy/paste
also works. This latest result is user-reported, not a newly instrumented request.
It weakens the hypothesis that pasted text alone causes the observed denial. The
current evidence is a difference between successful human-operated requests and
failed automated requests, not proof of a particular bot detector or a 100% detection
rate. Event handling, editor/request readiness, session state and automation-related
validation have not been isolated from one another. Earlier manual success inside
the proxy browser also argues against unconditional denial of that browser session.
No new generation, identity/security change, or retry was made for this update.

## Follow-up: read-only submission diagnostics and real HTTP denial

At 06:59 KST, a bounded native-UI control used the official model picker for
3.8 Flash / Low, tools off, a closed settings panel, and the literal 22-character
`reply with exactly OK.` prompt. Before the single normal Run click, read-only
observations showed document readiness complete, a visible/focused editor, an
enabled/uncovered Run button and an already completed **CountTokens HTTP 200**.
The existing UI network traffic then showed **GenerateContent HTTP 403** alongside
the permission toast. Thus an open panel, disabled/covered Run button, or failure
to wait for that token-count request cannot alone explain this control's failure.
Reported user-activation fields do not prove equivalence with physical-input
security events. Nothing was changed to spoof those fields.

A 07:01 HTTP control reproduced the denial in 9.764 s, but exposed another proxy
bug: it translated the provider denial into retryable-looking HTTP 502. The final
patch separates access denial from generic generation errors and pauses further
automatic submissions, including requests already waiting in the local queue.

At 07:07 KST the final live text-only check, with explicit 3.8 Flash / Low / tools
off, returned **HTTP 403 / retryable=false in 11.051 s**. The received rejection
body was 44 characters and not recognized as standard JSON. Sanitized diagnostics
contained no specific reason or automated-queries/unusual-traffic notice. Absence
of those notices does **not** rule out automation-related enforcement. Raw failure
text, request payloads, headers and credentials were not emitted by this diagnostic.

The worker/browser remained alive, but `/health` correctly returned 503 with
`generationAccess.status=denied`. One subsequent loopback request returned the same
403 in **0.002497 s**, without another prompt entry, Run click or GenerateContent
submission. The process was left running with submissions paused; it was not
restarted to clear denial. Final source-only tests additionally cover a vanished
toast: observed network denial remains 403 even if response location fails. This
last edge-case change was not loaded into the paused live process.

These are failure latencies, not throughput measurements. No successful automated
generation or image/parser comparison is claimed. The most useful remaining
distinction is successful human-operated requests versus denied automated requests,
not confirmed knowledge of the provider's detector. No browser-identity/security
changes, account switching, paid-key fallback, business-DB writes or credit charges
were made. Further live progress requires a permitted automated submission path;
repeating denied requests is not a compatibility fix. Offline package compatibility
checks can still proceed without contacting Google.

## Follow-up: Python package versus browser-engine versions

The user suggested rechecking the latest Camoufox. The actual installed engine,
152.0.4-beta.30, matches the [latest official browser release](https://github.com/daijro/camoufox/releases/tag/v152.0.4-beta.30),
but both dependency declarations still pin the **Python package to 0.4.11**.
The latest [PyPI package is 0.5.6](https://pypi.org/project/camoufox/0.5.6/), released
September 6. Updating Playwright/the browser did not update that wrapper. Therefore
these results do not establish failure with the latest complete software stack.
An isolated, no-Google compatibility check of the newer wrapper is the next local
diagnostic; an upgrade alone must not be represented as a verified permission fix.
The isolated 0.5.6 package was installed without changing the project environment;
39 targeted mocked/unit tests passed in 6.03 s. Source inspection found a concrete
upgrade concern not exercised by those mocks: its server keeps stdin open after a
newline-delimited configuration frame, while this fork's 0.4.11 bridge waits for EOF
before launching. A direct package bump would therefore hang that bridge. The new
package also changes browser-cache layout/cleanup behavior; do not call its default
browser resolver against the active legacy cache without reviewing migration.
No real-browser or Google-generation test on 0.5.6 was performed. The authenticated
live service remains on 0.4.11 with its denial latch intact.

## Repeatable checks

Final access-diagnostics unit run: **2,379 passed, 9 skipped, 68 integration-marked tests excluded**
in 65.74 s, with 59 warnings (including inherited unawaited-coroutine/deprecation
warnings). Ruff and targeted Pyright checks passed. This is not full integration
coverage; the real-browser no-Google fixture passed separately.

```sh
uv sync --locked --check
uv run ruff check .
uv run pytest --no-cov -m 'not integration'
uv run python scripts/browser_runtime_smoke.py
```

The app-side diagnostic transport and unchanged parser also passed 27 tests in
0.69 s in their separate repository. Do not confuse unit/fixture success with live Google QA.
Consult GETTING_STARTED.md and AGENTS.md before continuing; preserve all failure
evidence privately and never commit auth files, customer images, or full snapshots.
