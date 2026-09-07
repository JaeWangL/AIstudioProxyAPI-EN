"""Use Camoufox 0.5.6's public-API server, without deleting a legacy cache."""


def ensure_safe_browser_cache() -> None:
    from camoufox.multiversion import COMPAT_FLAG
    from camoufox.pkgman import INSTALL_DIR

    # The upstream default resolver/fetch CLI removes a nonempty pre-0.5 cache.
    # Refuse before calling it; our installer adds a versioned build side by side.
    if (
        INSTALL_DIR.is_dir()
        and any(INSTALL_DIR.iterdir())
        and not COMPAT_FLAG.is_file()
    ):
        raise RuntimeError(
            "Legacy Camoufox cache preserved. Run "
            "`uv run python scripts/install_camoufox.py` before launching; "
            "do not use the upstream fetch command to migrate an active cache."
        )


def configure_browser_server() -> None:
    import camoufox.server
    import camoufox.utils

    # Keep the package's own server script: 0.5.6 sends a newline-delimited
    # frame and holds stdin open, then closes the browser when stdin ends.
    # The old EOF-only shim would wait forever with this protocol.

    def launch_options(*args, **kwargs):
        ensure_safe_browser_cache()
        options = camoufox.utils.launch_options(*args, **kwargs)
        if options.get("proxy") is None:
            options.pop("proxy", None)
        return options

    setattr(camoufox.server, "launch_options", launch_options)
