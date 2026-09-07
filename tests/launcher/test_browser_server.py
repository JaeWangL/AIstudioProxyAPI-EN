import asyncio
import base64
import json
from pathlib import Path
from unittest.mock import patch

import camoufox.server
import pytest

from launcher.browser_server import configure_browser_server, ensure_safe_browser_cache


def test_public_launcher_and_null_proxy_compatibility():
    original_script = camoufox.server.LAUNCH_SCRIPT
    original_options = camoufox.server.launch_options
    try:
        configure_browser_server()
        assert camoufox.server.LAUNCH_SCRIPT == original_script
        assert Path(camoufox.server.LAUNCH_SCRIPT).is_file()
        script = Path(camoufox.server.LAUNCH_SCRIPT).read_text()
        assert "firefox.launchServer(options)" in script
        assert "require(path.join(driverPackage, 'index.js'))" in script
        with (
            patch("launcher.browser_server.ensure_safe_browser_cache"),
            patch(
                "camoufox.utils.launch_options",
                return_value={"proxy": None, "headless": True},
            ),
        ):
            assert camoufox.server.launch_options() == {"headless": True}
        with (
            patch("launcher.browser_server.ensure_safe_browser_cache"),
            patch(
                "camoufox.utils.launch_options",
                return_value={"proxy": {"server": "http://localhost:8000"}},
            ),
        ):
            assert (
                camoufox.server.launch_options()["proxy"]["server"]
                == "http://localhost:8000"
            )
    finally:
        camoufox.server.LAUNCH_SCRIPT = original_script
        camoufox.server.launch_options = original_options


def test_legacy_cache_is_preserved_before_options_are_built(tmp_path):
    marker = tmp_path / "legacy-browser.txt"
    marker.write_text("keep")
    with (
        patch("camoufox.pkgman.INSTALL_DIR", tmp_path),
        patch("camoufox.multiversion.COMPAT_FLAG", tmp_path / ".0.5_FLAG"),
    ):
        with pytest.raises(RuntimeError, match="Legacy Camoufox cache preserved"):
            ensure_safe_browser_cache()
    assert marker.read_text() == "keep"


@pytest.mark.parametrize("managed", [False, True])
def test_empty_or_versioned_cache_can_launch(tmp_path, managed):
    flag = tmp_path / ".0.5_FLAG"
    if managed:
        flag.touch()
    with (
        patch("camoufox.pkgman.INSTALL_DIR", tmp_path),
        patch("camoufox.multiversion.COMPAT_FLAG", flag),
    ):
        ensure_safe_browser_cache()


@pytest.mark.asyncio
async def test_official_server_launches_before_stdin_eof_and_closes_after_it(tmp_path):
    # A real Node process tests the new framing/lifecycle contract; no browser,
    # browser cache, network, Google session, or third-party package download.
    (tmp_path / "index.js").write_text(
        """module.exports = {firefox: {launchServer: async options => {
          if (options.host !== '127.0.0.1') throw new Error('host not passed');
          return {wsEndpoint: () => 'ws://127.0.0.1:1/fixture',
            close: async () => console.log('FIXTURE_CLOSED')};
        }}};"""
    )
    process = await asyncio.create_subprocess_exec(
        camoufox.server.get_nodejs(),
        str(camoufox.server.LAUNCH_SCRIPT),
        str(tmp_path),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        assert process.stdin is not None
        assert process.stdout is not None
        encoded = base64.b64encode(json.dumps({"host": "127.0.0.1"}).encode())
        process.stdin.write(encoded + b"\n")
        await process.stdin.drain()

        async def read_endpoint():
            while line := await process.stdout.readline():
                if b"ws://127.0.0.1:1/fixture" in line:
                    return
            raise AssertionError("Server exited without reporting its endpoint")

        # The old EOF-only shim would block here, with stdin still open.
        await asyncio.wait_for(read_endpoint(), timeout=5)
        assert process.returncode is None
        process.stdin.close()
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=5)
        assert process.returncode == 0, stderr.decode()
        assert b"FIXTURE_CLOSED" in stdout
    finally:
        if process.returncode is None:
            process.kill()
        await process.wait()
