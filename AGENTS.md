# Scope and handoff

This is JaeWangL's maintained fork of MasuRii/AIstudioProxyAPI-EN. Start with
GETTING_STARTED.md. Keep fixes reproducible in source control, not only in `/tmp`
or installed packages. Use `uv sync --locked`; update both supported lockfiles when
changing dependencies. Do not infer compatibility from version numbers alone.

Use actual DOM evidence for UI changes. Verify the rendered model and requested
parameters before sending a prompt; localStorage/cache/HTTP 200 is insufficient.
Never normalize malformed model output to turn a failed segmentation into success.
Preserve the caller's prompt/image bytes and its existing parser/failure policy.
An advertised/rendered model is not proof of generation permission. A permission-denied
provider response requires human access review; do not rotate accounts, select a paid key,
or retry indefinitely. Read COMPATIBILITY_REPORT.md before resuming live comparisons.

Google login and billing choices are human actions. Keep diagnostic runs loopback-only;
never copy another browser's cookies or commit auth files, logs, HTML snapshots,
customer images, Google account identifiers, or local paths. Do not enable account rotation,
paid API fallback, external helpers, or billing to make a comparison pass.

Test both launchers' shared browser bridge, collapsed/late/missing settings panels,
model mismatch (including the already-set fast path), and failed parameter readback.
Run the no-login browser smoke and the unchanged application parser tests. Report
mocked/local-fixture verification separately from live Google requests and image quality.
State any unverified Linux/runtime/provider behavior explicitly.
