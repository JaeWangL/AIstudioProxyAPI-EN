from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from scripts.install_camoufox import VERIFIED_BROWSER_VERSION, install_browser


def asset(*, sha256="a" * 64, prerelease=False, version=VERIFIED_BROWSER_VERSION):
    return SimpleNamespace(
        version=SimpleNamespace(full_string=version),
        sha256=sha256,
        is_prerelease=prerelease,
    )


def test_install_only_verified_official_build_without_replacing_legacy():
    repository = SimpleNamespace(repos=["unexpected/mirror"])
    selected = asset()
    with (
        patch(
            "scripts.install_camoufox.RepoConfig.find_by_name", return_value=repository
        ),
        patch(
            "scripts.install_camoufox.list_available_versions", return_value=[selected]
        ) as versions,
        patch("scripts.install_camoufox.CamoufoxFetcher") as fetcher,
    ):
        install_browser()
    assert repository.repos == ["daijro/camoufox"]
    versions.assert_called_once_with(repo_config=repository, include_prerelease=False)
    fetcher.assert_called_once_with(repo_config=repository, selected_version=selected)
    fetcher.return_value.install.assert_called_once_with(replace=False)
    fetcher.return_value.cleanup.assert_not_called()


@pytest.mark.parametrize(
    "items",
    [[], [asset(sha256=None)], [asset(prerelease=True)], [asset(version="old")]],
)
def test_missing_or_unverified_browser_is_not_installed(items):
    with (
        patch(
            "scripts.install_camoufox.RepoConfig.find_by_name", return_value=MagicMock()
        ),
        patch("scripts.install_camoufox.list_available_versions", return_value=items),
        patch("scripts.install_camoufox.CamoufoxFetcher") as fetcher,
    ):
        with pytest.raises(RuntimeError):
            install_browser()
    fetcher.assert_not_called()
