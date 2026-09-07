"""Explicit provider capabilities, not inferred from a successful HTTP response."""


def uses_fixed_sampling(model_id):
    # Verified against the 2026-09-03 Google 3.8 migration guide and live UI.
    # Do not extrapolate this rule to unknown future models or aliases.
    return model_id == "gemini-3.8-flash"


def validate_model_parameters(model_id, params):
    if not uses_fixed_sampling(model_id):
        return
    unsupported = [
        key for key in ("temperature", "top_p", "top_k") if params.get(key) is not None
    ]
    if unsupported:
        raise ValueError(
            "gemini-3.8-flash does not support sampling overrides; explicitly omit "
            + ", ".join(unsupported)
        )
    effort = params.get("reasoning_effort")
    if effort is not None and effort not in ("low", "medium", "high"):
        raise ValueError(
            "gemini-3.8-flash supports reasoning_effort low, medium or high"
        )
