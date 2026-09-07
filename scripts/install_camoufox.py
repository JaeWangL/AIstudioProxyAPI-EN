"""Install a verified official browser beside legacy files, never erase their root.

Unlike Camoufox 0.5.6's fetch CLI, this calls the versioned installer directly.
It does not access browser profiles, authentication, or an AI service.
"""

import argparse

from camoufox.pkgman import CamoufoxFetcher, RepoConfig, list_available_versions

VERIFIED_BROWSER_VERSION = "152.0.4-beta.30"


def install_browser(version: str = VERIFIED_BROWSER_VERSION) -> None:
    repository = RepoConfig.find_by_name("Official")
    if repository is None:
        raise RuntimeError("Official Camoufox repository configuration unavailable")
    # No mirror fallback or spoofed platform/architecture in this installer.
    repository.repos = ["daijro/camoufox"]
    versions = list_available_versions(repo_config=repository, include_prerelease=False)
    selected = next(
        (
            item
            for item in versions
            if item.version.full_string == version and not item.is_prerelease
        ),
        None,
    )
    if selected is None:
        raise RuntimeError(
            f"Official stable browser {version} unavailable for this host"
        )
    if not selected.sha256:
        raise RuntimeError(
            "Official browser asset has no SHA-256 digest; not installing"
        )
    fetcher = CamoufoxFetcher(repo_config=repository, selected_version=selected)
    # This method writes only a versioned directory and package-manager metadata.
    # Never call fetcher.cleanup(), extract_zip(), or the destructive fetch CLI.
    fetcher.install(replace=False)
    print(f"Official Camoufox {version} ready; existing legacy files preserved.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default=VERIFIED_BROWSER_VERSION)
    install_browser(parser.parse_args().version)
