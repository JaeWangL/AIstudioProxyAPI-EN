# Scope and handoff

This is JaeWangL's maintained fork of MasuRii/AIstudioProxyAPI-EN. Start with
GETTING_STARTED.md. Keep fixes reproducible in source control, not only in `/tmp`
or installed packages. Use `uv sync --locked`; update both supported lockfiles when
changing dependencies. Do not infer compatibility from version numbers alone.
The browser engine and Python wrapper have separate versions. This branch pins
camoufox 0.5.6 and Playwright 1.62.0; the verified browser is 152.0.4-beta.30.
Use `scripts/install_camoufox.py`, not the upstream fetch CLI, for a non-destructive
side-by-side browser installation. Launch refuses an unmigrated nonempty legacy cache.
Both launchers retain the package's official newline-framed public server script;
do not restore the deleted EOF-only shim. Never change a running service's Python
environment in place: use an isolated environment for compatibility experiments.

Use actual DOM evidence for UI changes. Verify the rendered model and requested
parameters before sending a prompt; localStorage/cache/HTTP 200 is insufficient.
The main controller must close the responsive settings panel and use one normal
actionability-checked Run click. Do not fall back to hotkeys, forced/DOM clicks,
or reload-and-resubmit when that click is blocked or its result is uncertain.
Never normalize malformed model output to turn a failed segmentation into success.
Preserve the caller's prompt/image bytes and its existing parser/failure policy.
Check the editor value after entry and again immediately before Run. This verifies
the prepared UI prompt, not equivalence with the caller's messages: the inherited
formatter adds role labels/newlines and strips outer whitespace. Report that boundary.
Physical typing succeeded in a diagnostic control, and the user also reports that
manual copy/paste succeeds; sequential Playwright input and native key entry failed.
Automation-related handling is a plausible cause, not confirmed detector evidence.
Read-only diagnostics confirmed a GenerateContent HTTP 403 even with a visible,
focused editor, enabled/uncovered Run button and completed CountTokens HTTP 200.
These UI observations do not prove security-event equivalence with physical input.
Do not claim a copy/paste fix, append sentinel characters, imitate human timing,
or modify browser identity/security to force success.
An advertised/rendered model is not proof of generation permission. A permission-denied
provider response requires human access review; do not rotate accounts, select a paid key,
or retry indefinitely. Read COMPATIBILITY_REPORT.md before resuming live comparisons.

GenerateContent HTTP 403 or the exact permission-denied toast latches automatic
submissions off. New requests fail locally with 403 / retryable=false. `/health`
returns 503 with generationAccess.status=denied even while the process/browser are
alive: this is provider readiness, not a process crash. Do not configure a supervisor
to restart repeatedly to clear this in-memory latch. An observed GenerateContent 200
(for example, a human-operated request after access review) clears it but proves
neither content/parser success nor restored permission for automation.
Optional SUBMISSION_DIAGNOSTICS=true enables read-only submission state and sanitized
RPC/error metadata, plus a loopback-client-only diagnostics endpoint. It is off by
default. Never add request bodies, headers, credentials, raw error text, or prompt
text to these diagnostic records; inherited snapshots still require private handling.

Google login and billing choices are human actions. Keep diagnostic runs loopback-only;
never copy another browser's cookies or commit auth files, logs, HTML snapshots,
customer images, Google account identifiers, or local paths. Do not enable account rotation,
paid API fallback, external helpers, or billing to make a comparison pass.

Test both launchers' shared browser bridge, collapsed/late/missing settings panels,
model mismatch (including the already-set fast path), and failed parameter readback.
Run the no-login browser smoke and the unchanged application parser tests. Report
mocked/local-fixture verification separately from live Google requests and image quality.
State any unverified Linux/runtime/provider behavior explicitly.
