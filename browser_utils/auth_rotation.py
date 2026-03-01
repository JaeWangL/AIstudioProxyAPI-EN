import asyncio
import glob
import json
import logging
import os
import random
import time
from datetime import datetime, timedelta
from typing import Optional

from playwright.async_api import Page, TimeoutError

from api_utils.server_state import state
from api_utils.utils_ext.cooldown_manager import (
    load_cooldown_profiles,
    save_cooldown_profiles,
)
from api_utils.utils_ext.usage_tracker import get_profile_usage
from config import AI_STUDIO_URL_PATTERN
from config.global_state import GlobalState
from config.selectors import INPUT_SELECTOR, SUBMIT_BUTTON_SELECTOR
from config.settings import (
    AUTO_ROTATE_AUTH_PROFILE,
    HIGH_TRAFFIC_QUEUE_THRESHOLD,
    ROTATION_DEPLETION_GUARD_HIGH_TRAFFIC,
)
from config.timeouts import QUOTA_EXCEEDED_COOLDOWN_SECONDS, RATE_LIMIT_COOLDOWN_SECONDS

logger = logging.getLogger("AuthRotation")

# Track recently used profiles to avoid rapid cycling/reuse
# Maps filename -> timestamp of last use
_USED_PROFILES_HISTORY = {}
_HISTORY_RETENTION_SECONDS = 3600 * 2  # 2 hours retention for history

# Profiles currently in cooldown (e.g. due to quota limit)
# Maps filename -> Dict[model_id, expiry_timestamp] OR filename -> expiry_timestamp (legacy/global)
_COOLDOWN_PROFILES = load_cooldown_profiles()

# [FINAL-02] Depletion Guard: Track rotation attempts
_ROTATION_TIMESTAMPS = []
_ROTATION_LIMIT_WINDOW = 60  # seconds
_ROTATION_LIMIT_COUNT = 3  # max attempts per window

# Dedicated marker to make post-rotation readiness stage easy to grep in logs.
_POST_ROTATION_READY_LOG_MARKER = "[POST-ROTATION-READY-CHECK]"


def _is_google_login_url(url: str) -> bool:
    """Return True when URL points to Google auth/account chooser pages."""
    if not url:
        return False

    lowered = url.lower()
    return (
        "accounts.google.com" in lowered
        or "/signin" in lowered
        or "servicelogin" in lowered
        or "accountchooser" in lowered
    )


def _normalize_model_id(model_id: str) -> str:
    """Normalize model IDs for cooldown lookups while preserving suffixes.

    Examples:
    - "gemini 3.1 pro preview" -> "gemini-3.1-pro-preview"
    - "gemini-2-5-pro" -> "gemini-2.5-pro"
    """
    if not model_id:
        return "default"

    normalized = model_id.strip().lower()
    normalized = normalized.replace("_", "-")
    normalized = normalized.replace(" ", "-")
    normalized = normalized.replace("--", "-")

    # Preserve known Gemini version segments while keeping trailing suffixes intact.
    normalized = normalized.replace("gemini-1-5-", "gemini-1.5-")
    normalized = normalized.replace("gemini-2-5-", "gemini-2.5-")
    normalized = normalized.replace("gemini-3-1-", "gemini-3.1-")

    if normalized.endswith("gemini-1-5-pro"):
        normalized = normalized.replace("gemini-1-5-pro", "gemini-1.5-pro")
    if normalized.endswith("gemini-2-5-pro"):
        normalized = normalized.replace("gemini-2-5-pro", "gemini-2.5-pro")
    if normalized.endswith("gemini-3-1-pro"):
        normalized = normalized.replace("gemini-3-1-pro", "gemini-3.1-pro")

    # Final normalization pass for consistency.
    normalized = normalized.replace("..", ".")
    normalized = normalized.strip("-")

    return normalized or "default"


def _canonicalize_profile_path(profile_path: str) -> str:
    """Canonicalize profile path so cooldown checks are stable across path formats."""
    if not profile_path:
        return ""
    try:
        return os.path.normcase(os.path.abspath(os.path.normpath(profile_path)))
    except Exception:
        # Keep original value as a safe fallback for callers.
        return profile_path


def _profile_keys_for_lookup(profile_path: str) -> list[str]:
    """Return lookup keys for profile cooldown/history maps."""
    if not profile_path:
        return []

    canonical = _canonicalize_profile_path(profile_path)
    if canonical == profile_path:
        return [profile_path]
    return [profile_path, canonical]


def _to_timestamp(value) -> Optional[float]:
    """Safely convert datetime/number values to unix timestamps."""
    try:
        ts = value.timestamp() if hasattr(value, "timestamp") else float(value)
        if isinstance(ts, (int, float)):
            return float(ts)
    except Exception:
        return None
    return None


def _get_profile_cooldown_entry(profile_path: str):
    """Fetch cooldown entry using canonicalized and legacy path keys."""
    for key in _profile_keys_for_lookup(profile_path):
        if key in _COOLDOWN_PROFILES:
            return _COOLDOWN_PROFILES[key], key

    # Backward-compatible fallback: match any existing key that canonicalizes
    # to the same profile path (handles legacy relative/absolute key mixes).
    target_canonical = _canonicalize_profile_path(profile_path)
    for existing_key, existing_value in _COOLDOWN_PROFILES.items():
        if _canonicalize_profile_path(existing_key) == target_canonical:
            return existing_value, existing_key

    return None, None


def _set_profile_cooldown_entry(profile_path: str, value) -> str:
    """Set cooldown entry while preserving caller key format for compatibility."""
    canonical_key = _canonicalize_profile_path(profile_path)
    primary_key = profile_path if isinstance(profile_path, str) and profile_path else canonical_key

    # Remove stale aliases that point to the same canonical path.
    stale_keys = [
        key
        for key in _COOLDOWN_PROFILES
        if key != primary_key and _canonicalize_profile_path(key) == canonical_key
    ]
    for stale_key in stale_keys:
        _COOLDOWN_PROFILES.pop(stale_key, None)

    _COOLDOWN_PROFILES[primary_key] = value
    return primary_key


def _prune_profile_history(now: float) -> None:
    """Trim stale history entries to keep in-memory history bounded."""
    expired_keys = [
        key
        for key, last_used_ts in _USED_PROFILES_HISTORY.items()
        if not isinstance(last_used_ts, (int, float))
        or now - last_used_ts > _HISTORY_RETENTION_SECONDS
    ]
    for key in expired_keys:
        _USED_PROFILES_HISTORY.pop(key, None)


def _mark_profile_recent_use(profile_path: str, used_at: Optional[float] = None) -> None:
    """Record profile usage for anti-thrashing selection behavior."""
    ts = used_at if isinstance(used_at, (int, float)) else time.time()
    _USED_PROFILES_HISTORY[_canonicalize_profile_path(profile_path)] = ts


def _is_profile_recently_used(profile_path: str, now: float, window_seconds: int) -> bool:
    """Check whether profile was used recently."""
    last_used = _USED_PROFILES_HISTORY.get(_canonicalize_profile_path(profile_path))
    return isinstance(last_used, (int, float)) and (now - last_used) < window_seconds


def _calculate_smart_priority(
    profile_path: str, target_model_id: str, cooldown_dict: dict
) -> tuple:
    """Calculate profile selection priority using efficiency + wear-leveling."""
    efficiency_score = 0
    now = time.time()

    # Check cooldown data for this profile (canonicalized lookup first).
    data = None
    canonical_path = _canonicalize_profile_path(profile_path)
    if canonical_path in cooldown_dict:
        data = cooldown_dict[canonical_path]
    elif profile_path in cooldown_dict:
        data = cooldown_dict[profile_path]

    if isinstance(data, dict):
        for model, ts in data.items():
            if model == "global":
                continue
            if target_model_id and model == target_model_id:
                continue

            ts_val = _to_timestamp(ts)
            if ts_val is not None and ts_val > now:
                efficiency_score += 1

    usage = get_profile_usage(profile_path)

    # Sort order:
    # 1) Higher efficiency first  -> negative for ascending sort
    # 2) Lower usage first
    # 3) Random tie-breaker
    return (-efficiency_score, usage, random.random())


def check_profile_cookie_health(profile_path: str) -> dict:
    """
    Check the health of cookies in an auth profile.

    Returns a dict with:
    - total: total number of cookies
    - expired: number of expired cookies
    - valid: number of valid cookies
    - critical_expired: list of critical expired cookie names (auth-related)
    - health_status: 'healthy', 'warning', or 'critical'
    """
    result = {
        "total": 0,
        "expired": 0,
        "valid": 0,
        "session": 0,
        "critical_expired": [],
        "health_status": "healthy",
    }

    # Critical cookies that affect authentication
    CRITICAL_COOKIES = {
        "SID",
        "HSID",
        "SSID",
        "APISID",
        "SAPISID",
        "SIDCC",
        "__Secure-1PSID",
        "__Secure-3PSID",
    }

    try:
        with open(profile_path, encoding="utf-8") as f:
            data = json.load(f)

        cookies = data.get("cookies", [])
        result["total"] = len(cookies)
        now = time.time()

        for cookie in cookies:
            name = cookie.get("name", "")
            expires = cookie.get("expires", -1)

            if expires == -1:
                # Session cookie (no expiry)
                result["session"] += 1
                result["valid"] += 1
            elif expires < now:
                # Expired
                result["expired"] += 1
                if name in CRITICAL_COOKIES:
                    result["critical_expired"].append(name)
            else:
                # Valid
                result["valid"] += 1

        # Determine health status
        if result["critical_expired"]:
            result["health_status"] = "critical"
            logger.warning(
                f"🔴 Auth profile '{os.path.basename(profile_path)}' has expired critical cookies: {result['critical_expired']}"
            )
        elif result["expired"] > result["total"] * 0.3:  # More than 30% expired
            result["health_status"] = "warning"
            logger.warning(
                f"🟡 Auth profile '{os.path.basename(profile_path)}' has {result['expired']}/{result['total']} expired cookies"
            )
        else:
            logger.debug(
                f"🟢 Auth profile '{os.path.basename(profile_path)}' cookie health: {result['valid']}/{result['total']} valid"
            )

    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"Failed to check cookie health for '{profile_path}': {e}")
        result["health_status"] = "error"

    return result


def _find_best_profile_in_dirs(
    directories: list[str],
    target_model_id: str = None,
    exclude_profiles: Optional[set[str]] = None,
) -> Optional[str]:
    """Find the best available profile in directories with robust cooldown checks."""
    if not directories or not isinstance(directories, list):
        return None

    logger.info(f"[DEBUG] Scanning directories: {directories}")

    excluded_canonical = {
        _canonicalize_profile_path(p)
        for p in (exclude_profiles or set())
        if isinstance(p, str) and p
    }

    all_profiles: list[str] = []
    seen_profiles: set[str] = set()
    for d in directories:
        if d and isinstance(d, str) and os.path.exists(d):
            files = glob.glob(os.path.join(d, "*.json"))
            logger.info(f"[DEBUG] Found {len(files)} profiles in {d}")
            for file_path in files:
                canonical = _canonicalize_profile_path(file_path)
                if canonical not in seen_profiles:
                    seen_profiles.add(canonical)
                    all_profiles.append(canonical)
        else:
            logger.warning(
                f"[DEBUG] Directory missing or invalid: {d} (Abs: {os.path.abspath(d) if d else 'None'})"
            )

    if not all_profiles:
        logger.warning(f"[DEBUG] No profiles found in {directories}")
        return None

    normalized_target_model = (
        _normalize_model_id(target_model_id) if target_model_id else None
    )
    logger.info(
        f"[DEBUG] Target model: {target_model_id} -> Normalized: {normalized_target_model}"
    )

    valid_profiles: list[str] = []
    now = time.time()
    _prune_profile_history(now)

    model_keys_to_check: list[str] = []
    if normalized_target_model:
        model_keys_to_check.append(normalized_target_model)
    if target_model_id:
        model_keys_to_check.append(target_model_id.lower())

    # Preserve order while removing duplicates.
    model_keys_to_check = list(dict.fromkeys(model_keys_to_check))

    for profile_path in all_profiles:
        if not os.path.exists(profile_path):
            continue

        if profile_path in excluded_canonical:
            logger.debug(
                f"[DEBUG] Excluding profile {os.path.basename(profile_path)} (already attempted in this cycle)"
            )
            continue

        cooldown_data, _ = _get_profile_cooldown_entry(profile_path)
        is_cooldown_active = False

        if isinstance(cooldown_data, dict):
            global_ts = _to_timestamp(cooldown_data.get("global"))
            if global_ts is not None and global_ts > now:
                is_cooldown_active = True

            if not is_cooldown_active:
                for model_key in model_keys_to_check:
                    if model_key in cooldown_data:
                        model_ts = _to_timestamp(cooldown_data.get(model_key))
                        if model_ts is not None and model_ts > now:
                            is_cooldown_active = True
                            logger.info(
                                f"[DEBUG] Profile {os.path.basename(profile_path)} is in cooldown for model '{model_key}'"
                            )
                            break
        elif cooldown_data is not None:
            legacy_ts = _to_timestamp(cooldown_data)
            if legacy_ts is not None and legacy_ts > now:
                is_cooldown_active = True

        if is_cooldown_active:
            continue

        valid_profiles.append(profile_path)

    if not valid_profiles:
        return None

    # Anti-thrashing: avoid reusing a just-used profile when alternatives exist.
    recent_use_window_seconds = 90
    candidate_profiles = valid_profiles
    if len(valid_profiles) > 1:
        non_recent = [
            p
            for p in valid_profiles
            if not _is_profile_recently_used(p, now, recent_use_window_seconds)
        ]
        if non_recent:
            candidate_profiles = non_recent
        else:
            # If all are recent, pick least-recently-used first to spread load.
            candidate_profiles = sorted(
                valid_profiles,
                key=lambda p: _USED_PROFILES_HISTORY.get(
                    _canonicalize_profile_path(p), 0.0
                ),
            )

    candidate_profiles.sort(
        key=lambda p: _calculate_smart_priority(
            p, normalized_target_model, _COOLDOWN_PROFILES
        )
    )

    logger.info(
        f"[DEBUG] Best profile selected: {os.path.basename(candidate_profiles[0])}"
    )
    return candidate_profiles[0]


def _get_next_profile(
    target_model_id: str = None,
    exclude_profiles: Optional[set[str]] = None,
) -> Optional[str]:
    """Select next profile from standard pool first, then emergency pool."""
    emergency_dir = "auth_profiles/emergency"
    abs_emergency = os.path.abspath(emergency_dir)
    logger.info(f"[DEBUG] Emergency Dir: {emergency_dir} (Absolute: {abs_emergency})")
    os.makedirs(emergency_dir, exist_ok=True)

    logger.info(
        f"Tier 1: Searching for standard profiles... (Target Model: {target_model_id or 'Any'})"
    )
    standard_dirs = [
        "auth_profiles/saved",
        "auth_profiles/active",
        "auth_profiles/emergency",
    ]
    best_profile = _find_best_profile_in_dirs(
        standard_dirs,
        target_model_id,
        exclude_profiles=exclude_profiles,
    )

    if best_profile:
        usage_val = get_profile_usage(best_profile)
        logger.info(
            f"🎯 Selected standard profile '{os.path.basename(best_profile)}' with usage: {usage_val}"
        )
        return best_profile

    logger.warning("Tier 1 yielded no profiles. Falling back to Tier 2: Emergency Pool.")
    emergency_dirs = [emergency_dir]
    best_emergency_profile = _find_best_profile_in_dirs(
        emergency_dirs,
        target_model_id,
        exclude_profiles=exclude_profiles,
    )

    if best_emergency_profile:
        usage_val = get_profile_usage(best_emergency_profile)
        logger.info(
            f"🚨 Selected emergency profile '{os.path.basename(best_emergency_profile)}' with usage: {usage_val}"
        )
        return best_emergency_profile

    logger.error("No available profiles in standard or emergency pools.")
    return None


async def verify_post_rotation_page_ready(
    page: Optional[Page] = None,
    req_id: str = "",
    *,
    max_attempts: int = 2,
) -> bool:
    """Verify critical page elements are ready before retrying requests.

    This is used after auth rotation to ensure browser automation is in a usable
    state (input container, textarea, and submit button are visible).
    """
    if page is None:
        page = state.page_instance

    req_prefix = f"[{req_id}] " if req_id else ""

    if not page or page.is_closed():
        logger.error(
            f"{req_prefix}{_POST_ROTATION_READY_LOG_MARKER} page unavailable"
        )
        return False

    if GlobalState.IS_SHUTTING_DOWN.is_set():
        logger.info(
            f"{req_prefix}{_POST_ROTATION_READY_LOG_MARKER} skipped during shutdown"
        )
        return True

    from playwright.async_api import expect as expect_async

    from config.selector_utils import (
        INPUT_WRAPPER_SELECTORS,
        find_first_visible_locator,
    )

    target_url = f"https://{AI_STUDIO_URL_PATTERN}prompts/new_chat"

    for attempt in range(1, max_attempts + 1):
        try:
            current_url = page.url if hasattr(page, "url") else ""
            if _is_google_login_url(current_url):
                raise RuntimeError(
                    "Redirected to Google sign-in page (pre-navigation)"
                )

            if AI_STUDIO_URL_PATTERN not in current_url or "/prompts/" not in current_url:
                logger.warning(
                    f"{req_prefix}{_POST_ROTATION_READY_LOG_MARKER} attempt {attempt}/{max_attempts}: unexpected URL '{current_url}', navigating to chat page"
                )
                await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)

            post_nav_url = page.url if hasattr(page, "url") else ""
            if _is_google_login_url(post_nav_url):
                raise RuntimeError(
                    "Redirected to Google sign-in page (post-navigation)"
                )

            input_wrapper_locator, matched_selector = await find_first_visible_locator(
                page,
                INPUT_WRAPPER_SELECTORS,
                description="Rotation Input Container",
                timeout_per_selector=20000,
            )
            if not input_wrapper_locator:
                raise RuntimeError("Input container not visible")

            await expect_async(page.locator(INPUT_SELECTOR).first).to_be_visible(
                timeout=10000
            )

            submit_locator = page.locator(SUBMIT_BUTTON_SELECTOR)
            if await submit_locator.count() <= 0:
                raise RuntimeError("Submit button not found")

            await expect_async(submit_locator.first).to_be_visible(timeout=10000)

            logger.info(
                f"{req_prefix}{_POST_ROTATION_READY_LOG_MARKER} ✅ verified (input selector: {matched_selector})"
            )
            return True

        except asyncio.CancelledError:
            raise
        except Exception as ready_err:
            logger.warning(
                f"{req_prefix}{_POST_ROTATION_READY_LOG_MARKER} attempt {attempt}/{max_attempts} failed: {ready_err}"
            )
            if attempt >= max_attempts:
                break

            try:
                await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
            except Exception as nav_err:
                logger.debug(
                    f"{req_prefix}{_POST_ROTATION_READY_LOG_MARKER} recovery navigation failed: {nav_err}"
                )
            await asyncio.sleep(1)

    logger.error(
        f"{req_prefix}{_POST_ROTATION_READY_LOG_MARKER} ❌ verification failed"
    )
    return False


async def _perform_canary_test(page: Page) -> bool:
    """
    Performs a simple check to ensure the new profile is healthy.
    Navigates to the chat page and verifies a key element is present.
    """
    if not page or page.is_closed():
        logger.warning("⚠️ Canary Test: Page is not available.")
        return False

    # Early exit during shutdown to avoid proxy connection issues
    if GlobalState.IS_SHUTTING_DOWN.is_set():
        logger.info("🔬 Canary Test Skipped: System is shutting down.")
        return True  # Return True to allow rotation to complete during shutdown

    try:
        logger.info("🔬 Performing Canary Test on new profile...")
        target_url = f"https://{AI_STUDIO_URL_PATTERN}prompts/new_chat"
        await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)

        # Verify critical UI elements are actually ready before request retries.
        ready = await verify_post_rotation_page_ready(page=page, max_attempts=2)
        if not ready:
            logger.warning(
                f"{_POST_ROTATION_READY_LOG_MARKER} ❌ Canary failed: critical input elements not ready after rotation."
            )
            return False

        logger.info("✅ Canary Test Passed: Profile is healthy.")
        return True
    except TimeoutError:
        logger.warning(
            "❌ Canary Test Failed: Timed out waiting for key element. Profile is likely bad."
        )
        return False
    except Exception as e:
        # Special handling for proxy connection errors during shutdown
        if (
            "NS_ERROR_PROXY_CONNECTION_REFUSED" in str(e)
            and GlobalState.IS_SHUTTING_DOWN.is_set()
        ):
            logger.info(
                "🔬 Canary Test Skipped: Proxy connection refused during shutdown."
            )
            return True  # Allow rotation to complete during shutdown

        logger.error(f"❌ Canary Test Failed: Unexpected error - {e}", exc_info=True)
        return False


async def perform_auth_rotation(target_model_id: str = None) -> bool:
    """
    Performs the authentication profile rotation with a soft-swap and canary test.

    Checks AUTO_ROTATE_AUTH_PROFILE environment variable to determine if rotation should proceed.

    1. Acquires Hard Lock (stops requests).
    2. Enters a loop to find a healthy profile.
    3. Selects next profile, puts the old one in cooldown.
    4. Performs a soft-swap of cookies.
    5. Runs a canary test to validate the new profile.
    6. If healthy, breaks the loop and releases the lock.
    7. If unhealthy, adds the profile to cooldown and repeats.
    """

    # Check if auto-rotation is enabled via environment variable
    if not AUTO_ROTATE_AUTH_PROFILE:
        logger.info(
            "🔒 Auth rotation is disabled via AUTO_ROTATE_AUTH_PROFILE environment variable"
        )
        logger.info("♻️ ROTATION SKIPPED - Auto-rotation disabled")
        logger.info("♻️ =========================================")
        return False

    # [OBS-04] Explicit Rotation Logging with Visual Separators
    logger.info("♻️ =========================================")
    logger.info("♻️ INITIATING AUTH ROTATION")
    logger.info("♻️ =========================================")

    # Avoid re-entry if already rotating (Atomic Check & Wait)
    if not GlobalState.AUTH_ROTATION_LOCK.is_set():
        logger.info(
            "⚠️ Rotation already in progress (Lock is cleared). Waiting for completion..."
        )
        await GlobalState.AUTH_ROTATION_LOCK.wait()
        logger.info("♻️ Rotation skipped - already in progress (Waited for completion)")
        logger.info("♻️ =========================================")
        return True

    # Atomically acquire the lock
    GlobalState.AUTH_ROTATION_LOCK.clear()
    logger.info("🔒 Request processing locked.")

    # Signal a new rotation cycle for waiters.
    GlobalState.rotation_complete_event.clear()

    should_release_lock = True
    rotation_succeeded = False

    try:
        # [FINAL-02] Depletion Guard Check
        global _ROTATION_TIMESTAMPS
        current_time = time.time()

        # Dynamic "Rotation Window" Adjustment
        if GlobalState.queued_request_count > HIGH_TRAFFIC_QUEUE_THRESHOLD:
            effective_rotation_limit = ROTATION_DEPLETION_GUARD_HIGH_TRAFFIC
            logger.info(
                f"High traffic detected ({GlobalState.queued_request_count} queued). Using lenient rotation guard: {effective_rotation_limit}"
            )
        else:
            effective_rotation_limit = _ROTATION_LIMIT_COUNT

        # Filter timestamps within the window, ensuring we only process numeric values
        _ROTATION_TIMESTAMPS = [
            t
            for t in _ROTATION_TIMESTAMPS
            if isinstance(t, (int, float)) and current_time - t < _ROTATION_LIMIT_WINDOW
        ]

        if len(_ROTATION_TIMESTAMPS) >= effective_rotation_limit:
            logger.critical(
                f"🚨 CRITICAL: TOO MANY ROTATIONS! (limit: {effective_rotation_limit}) All accounts may be exhausted. Stopping Browser & Locking API."
            )
            logger.critical("♻️ ROTATION ABORTED - System Exhausted")
            logger.critical("♻️ =========================================")

            # SOFT DEPLETION STRATEGY: Avoid hard shutdown to maintain "No Downtime" goal
            logger.critical(
                "🚨 DEPLETION DETECTED: Switching to emergency operation mode"
            )
            logger.critical("🚨 All profiles exhausted, but avoiding hard shutdown")

            # Set emergency mode flag
            GlobalState.DEPLOYMENT_EMERGENCY_MODE = True

            # Try to perform soft profile rotation even during depletion
            # This maintains the "No Downtime" requirement
            try:
                # Attempt one final soft rotation with emergency profiles
                emergency_profile = _find_best_profile_in_dirs(
                    ["auth_profiles/emergency"]
                )
                if emergency_profile:
                    emergency_profile = _canonicalize_profile_path(emergency_profile)
                    logger.critical("🚨 Attempting emergency profile activation...")
                    # Perform minimal soft swap for emergency operation
                    if state.page_instance and not state.page_instance.is_closed():
                        with open(emergency_profile, encoding="utf-8") as f:
                            storage_state = json.load(f)
                        context = state.page_instance.context
                        await context.clear_cookies()
                        await context.add_cookies(storage_state.get("cookies", []))
                        state.current_auth_profile_path = emergency_profile
                        os.environ["ACTIVE_AUTH_JSON_PATH"] = emergency_profile
                        _mark_profile_recent_use(emergency_profile)
                        logger.critical(
                            "🚨 Emergency profile activated - continuing operation"
                        )
                        rotation_succeeded = True
                        return True
            except Exception as e:
                logger.critical(f"🚨 Emergency activation failed: {e}")

            # Only if soft emergency operation fails, then consider partial shutdown
            # But still try to maintain some level of service
            logger.critical(
                "🚨 Entering minimal operation mode - limited service available"
            )

            # PERMANENT LOCK (Do not release GlobalState.AUTH_ROTATION_LOCK)
            # We leave the lock cleared so no new requests can proceed.
            should_release_lock = False
            return False

        # Record this attempt
        _ROTATION_TIMESTAMPS.append(current_time)
        logger.info(
            f"🔄 Rotation attempt #{len(_ROTATION_TIMESTAMPS)} in current window"
        )

        # (Lock is already acquired above)

        max_retries = 5
        failed_attempts = 0
        attempted_profiles: set[str] = set()

        active_profile = getattr(state, "current_auth_profile_path", None)
        if active_profile and active_profile != "unknown":
            _mark_profile_recent_use(active_profile, used_at=current_time)

        while failed_attempts < max_retries:
            logger.info("🔍 Selecting next auth profile...")
            next_profile_path = _get_next_profile(
                target_model_id,
                exclude_profiles=attempted_profiles,
            )

            if not next_profile_path:
                logger.warning("All profiles are on cooldown. Calculating wait time...")

                now = time.time()
                min_expiry = float("inf")

                for cooldown_data in _COOLDOWN_PROFILES.values():
                    if isinstance(cooldown_data, dict):
                        for ts in cooldown_data.values():
                            ts_val = _to_timestamp(ts)
                            if ts_val is not None and now < ts_val < min_expiry:
                                min_expiry = ts_val
                    else:
                        ts_val = _to_timestamp(cooldown_data)
                        if ts_val is not None and now < ts_val < min_expiry:
                            min_expiry = ts_val

                if min_expiry != float("inf"):
                    wait_time = (min_expiry - now) + 1
                    if wait_time > 0:
                        logger.info(
                            f"🕒 Waiting for {wait_time:.2f} seconds for the next profile to become available."
                        )
                        await asyncio.sleep(wait_time)

                        logger.info("Retrying to get next profile after waiting.")
                        next_profile_path = _get_next_profile(
                            target_model_id,
                            exclude_profiles=attempted_profiles,
                        )

                if not next_profile_path:
                    logger.critical(
                        "❌ Rotation Failed: No available auth profiles found even after waiting!"
                    )
                    logger.critical("♻️ ROTATION FAILED - No profiles available")
                    logger.critical("♻️ =========================================")
                    return False

            next_profile_path = _canonicalize_profile_path(next_profile_path)
            attempted_profiles.add(next_profile_path)

            if failed_attempts == 0:
                old_profile = getattr(state, "current_auth_profile_path", "unknown")
                if old_profile and old_profile != "unknown" and os.path.exists(old_profile):
                    error_type = GlobalState.last_error_type

                    cooldown_entry, _ = _get_profile_cooldown_entry(old_profile)
                    if not isinstance(cooldown_entry, dict):
                        cooldown_entry = {}

                    expiry_ts = (
                        datetime.now()
                        + timedelta(seconds=QUOTA_EXCEEDED_COOLDOWN_SECONDS)
                    ).timestamp()
                    rate_limit_ts = (
                        datetime.now() + timedelta(seconds=RATE_LIMIT_COOLDOWN_SECONDS)
                    ).timestamp()

                    if error_type == "RATE_LIMIT":
                        cooldown_entry["global"] = rate_limit_ts
                        logger.info(
                            f"❄️ Placing profile in GLOBAL cooldown for {RATE_LIMIT_COOLDOWN_SECONDS}s (Rate Limit)."
                        )
                    else:
                        models_to_cooldown: set[str] = set()
                        logger.info(
                            f"🔍 Model cooldown analysis: exhausted_models={GlobalState.current_profile_exhausted_models}, target_model={target_model_id}"
                        )

                        for exhausted_model in GlobalState.current_profile_exhausted_models:
                            if isinstance(exhausted_model, str) and exhausted_model:
                                models_to_cooldown.add(exhausted_model.lower())
                                models_to_cooldown.add(
                                    _normalize_model_id(exhausted_model)
                                )

                        if target_model_id:
                            models_to_cooldown.add(target_model_id.lower())
                            models_to_cooldown.add(_normalize_model_id(target_model_id))

                        if not models_to_cooldown:
                            fallback_model = getattr(
                                state, "current_ai_studio_model_id", None
                            )
                            if fallback_model:
                                models_to_cooldown.add(fallback_model.lower())
                                models_to_cooldown.add(
                                    _normalize_model_id(fallback_model)
                                )
                                logger.info(
                                    f"🔍 Using state.current_ai_studio_model_id as fallback: {fallback_model}"
                                )
                            else:
                                logger.warning(
                                    "⚠️ Unable to identify specific model, falling back to 'default'. This should be rare."
                                )
                                models_to_cooldown.add("default")

                        logger.info(
                            f"🎯 Applying cooldown to models: {sorted(models_to_cooldown)}"
                        )
                        for model_id in models_to_cooldown:
                            cooldown_entry[model_id] = expiry_ts
                            logger.info(
                                f"❄️ Placing profile in cooldown for model '{model_id}' for {QUOTA_EXCEEDED_COOLDOWN_SECONDS}s."
                            )

                    _set_profile_cooldown_entry(old_profile, cooldown_entry)
                    save_cooldown_profiles(_COOLDOWN_PROFILES)

            new_profile_name = os.path.basename(next_profile_path)
            logger.info(f"👉 Attempting to rotate to profile: {new_profile_name}")

            state.current_auth_profile_path = next_profile_path
            os.environ["ACTIVE_AUTH_JSON_PATH"] = next_profile_path

            logger.info("🚀 Performing Soft Context Swap...")
            if not state.page_instance or state.page_instance.is_closed():
                logger.error(
                    "❌ Page instance not found or closed, cannot perform soft swap."
                )
                return False

            try:
                try:
                    with open(next_profile_path, encoding="utf-8") as f:
                        storage_state = json.load(f)
                except (json.JSONDecodeError, OSError) as json_err:
                    logger.error(
                        f"❌ Corrupt or inaccessible profile file '{new_profile_name}': {json_err}"
                    )
                    raise

                if not isinstance(storage_state, dict):
                    raise ValueError(f"Invalid profile format in '{new_profile_name}'")

                context = state.page_instance.context
                await context.clear_cookies()
                await context.add_cookies(storage_state.get("cookies", []))
                logger.info("✅ Injected new cookies.")

                if await _perform_canary_test(state.page_instance):
                    GlobalState.reset_quota_status()
                    _mark_profile_recent_use(next_profile_path)
                    logger.info(
                        f"♻️ ROTATION SUCCESSFUL with profile: {new_profile_name}"
                    )
                    logger.info("♻️ =========================================")
                    rotation_succeeded = True
                    return True

                logger.warning(
                    f" Canary test failed for {new_profile_name}. Adding to cooldown and retrying."
                )
                failed_attempts += 1

                expiry_time = (
                    datetime.now() + timedelta(seconds=QUOTA_EXCEEDED_COOLDOWN_SECONDS)
                ).timestamp()
                _set_profile_cooldown_entry(next_profile_path, expiry_time)
                save_cooldown_profiles(_COOLDOWN_PROFILES)
                logger.info(
                    f"❄️ Placing unhealthy profile '{new_profile_name}' in cooldown for {QUOTA_EXCEEDED_COOLDOWN_SECONDS}s."
                )
                continue

            except Exception as swap_err:
                logger.error(
                    f"❌ Failed to perform soft swap for {new_profile_name}: {swap_err}"
                )
                failed_attempts += 1
                expiry_time = (
                    datetime.now() + timedelta(seconds=QUOTA_EXCEEDED_COOLDOWN_SECONDS)
                ).timestamp()
                _set_profile_cooldown_entry(next_profile_path, expiry_time)
                save_cooldown_profiles(_COOLDOWN_PROFILES)
                logger.info(
                    f"❄️ Placing swap-failed profile '{new_profile_name}' in cooldown."
                )
                continue

        # If loop finishes without success
        logger.critical(
            f"🚨 ROTATION FAILED: All {max_retries} attempts to find a healthy profile failed."
        )
        return False
    except asyncio.CancelledError:
        logger.warning("♻️ Rotation task cancelled.")
        raise
    except Exception as e:
        logger.error(
            f"❌ Unexpected error during auth rotation loop: {e}", exc_info=True
        )
        logger.error("♻️ ROTATION FAILED - Unexpected error")
        logger.error("♻️ =========================================")
        return False
    finally:
        # Record successful rotation completion time for downstream timeout guards.
        if rotation_succeeded:
            GlobalState.LAST_ROTATION_TIMESTAMP = time.time()
            logger.info(
                f"🕒 Rotation timestamp updated: {GlobalState.LAST_ROTATION_TIMESTAMP}"
            )

        # Wake any waiters that are blocked on rotation completion.
        GlobalState.rotation_complete_event.set()

        # 5. Release lock (if not permanently locked)
        if should_release_lock:
            GlobalState.AUTH_ROTATION_LOCK.set()
            logger.info("🔓 Request processing unlocked.")
            logger.info("♻️ Rotation flow completed")
            logger.info("♻️ =========================================")
