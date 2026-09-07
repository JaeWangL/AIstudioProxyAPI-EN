from pathlib import Path
from unittest.mock import patch

import camoufox.server

from launcher.browser_server import configure_browser_server


def test_public_launcher_and_null_proxy_compatibility():
    original_script = camoufox.server.LAUNCH_SCRIPT
    original_options = camoufox.server.launch_options
    try:
        configure_browser_server()
        assert Path(camoufox.server.LAUNCH_SCRIPT).is_file()
        script = Path(camoufox.server.LAUNCH_SCRIPT).read_text()
        assert "firefox.launchServer(options)" in script
        assert "browserServerImpl" not in script
        with patch(
            "camoufox.utils.launch_options",
            return_value={"proxy": None, "headless": True},
        ):
            assert camoufox.server.launch_options() == {"headless": True}
        with patch(
            "camoufox.utils.launch_options",
            return_value={"proxy": {"server": "http://localhost:8000"}},
        ):
            assert (
                camoufox.server.launch_options()["proxy"]["server"]
                == "http://localhost:8000"
            )
    finally:
        camoufox.server.LAUNCH_SCRIPT = original_script
        camoufox.server.launch_options = original_options
