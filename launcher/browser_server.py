"""Camoufox launch configuration with Playwright's public Node server API."""

from pathlib import Path


def configure_browser_server() -> None:
    import camoufox.server
    import camoufox.utils

    # Camoufox 0.4.11's bundled script imports lib/browserServerImpl.js, a
    # private file removed in newer Playwright releases. Keep its Python
    # configuration builder, but select our public-API bridge for both launchers.
    camoufox.server.LAUNCH_SCRIPT = Path(__file__).with_name("browser_server.cjs")

    def launch_options(*args, **kwargs):
        options = camoufox.utils.launch_options(*args, **kwargs)
        if options.get("proxy") is None:
            options.pop("proxy", None)
        return options

    setattr(camoufox.server, "launch_options", launch_options)
