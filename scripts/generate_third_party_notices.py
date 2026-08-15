from __future__ import annotations

import importlib.metadata as metadata
import platform
import re
import sqlite3
import ssl
import sys
from collections import deque
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "THIRD_PARTY_NOTICES.txt"
ROOT_DISTRIBUTION = "hf-gguf-downloader"
LICENSE_PREFIXES = ("license", "licence", "copying", "notice")


def _runtime_distributions() -> list[metadata.Distribution]:
    """Return the installed runtime dependency closure, excluding this project."""

    root = metadata.distribution(ROOT_DISTRIBUTION)
    queue = deque(root.requires or ())
    seen = {canonicalize_name(ROOT_DISTRIBUTION)}
    distributions: list[metadata.Distribution] = []

    while queue:
        requirement = Requirement(queue.popleft())
        if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
            continue

        normalized_name = canonicalize_name(requirement.name)
        if normalized_name in seen:
            continue

        distribution = metadata.distribution(requirement.name)
        seen.add(normalized_name)
        distributions.append(distribution)
        queue.extend(distribution.requires or ())

    return sorted(distributions, key=lambda item: canonicalize_name(item.metadata["Name"]))


def _license_expression(distribution: metadata.Distribution) -> str:
    value = distribution.metadata.get("License-Expression") or distribution.metadata.get("License")
    if value and "\n" not in value and len(value) <= 120:
        return value.strip()

    classifiers = distribution.metadata.get_all("Classifier") or ()
    licenses = [item.removeprefix("License :: ") for item in classifiers if item.startswith("License :: ")]
    return "; ".join(licenses) or "See the reproduced license text below"


def _upstream_url(distribution: metadata.Distribution) -> str:
    project_urls = distribution.metadata.get_all("Project-URL") or ()
    preferred_labels = ("source", "source code", "repository", "homepage", "home")
    parsed_urls: list[tuple[str, str]] = []

    for item in project_urls:
        label, separator, url = item.partition(",")
        if separator:
            parsed_urls.append((label.strip().lower(), url.strip()))

    for preferred_label in preferred_labels:
        for label, url in parsed_urls:
            if label == preferred_label:
                return url

    return distribution.metadata.get("Home-page") or _pypi_url(distribution)


def _pypi_url(distribution: metadata.Distribution) -> str:
    name = distribution.metadata["Name"]
    return f"https://pypi.org/project/{name}/{distribution.version}/#files"


def _license_files(distribution: metadata.Distribution) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []

    for package_path in distribution.files or ():
        filename = Path(str(package_path)).name.lower()
        if not filename.startswith(LICENSE_PREFIXES):
            continue

        path = Path(distribution.locate_file(package_path))
        if path.is_file():
            result.append((str(package_path).replace("\\", "/"), path.read_text("utf-8", errors="replace")))

    return sorted(result)


def _section(title: str, details: list[str], license_files: list[tuple[str, str]]) -> str:
    lines = ["=" * 79, title, "=" * 79, *details]
    for filename, contents in license_files:
        normalized_contents = "\n".join(line.rstrip() for line in contents.splitlines())
        lines.extend(("", f"--- {filename} ---", "", normalized_contents.rstrip()))
    return "\n".join(lines)


def _python_runtime_sections(apache_license: str) -> list[str]:
    base_prefix = Path(sys.base_prefix)
    python_license = base_prefix / "LICENSE.txt"
    if not python_license.is_file():
        raise FileNotFoundError(f"Cannot find the CPython license: {python_license}")
    python_release = platform.python_version().replace(".", "")

    sections = [
        _section(
            f"CPython {platform.python_version()}",
            [
                "License: Python Software Foundation License Version 2 and bundled component licenses",
                f"Source: https://www.python.org/downloads/release/python-{python_release}/",
            ],
            [("CPython LICENSE.txt", python_license.read_text("utf-8", errors="replace"))],
        )
    ]

    tk_license = base_prefix / "tcl" / "tk8.6" / "license.terms"
    if tk_license.is_file():
        sections.append(
            _section(
                "Tcl/Tk 8.6",
                [
                    "License: Tcl/Tk license",
                    "Source: https://www.tcl.tk/software/tcltk/download.html",
                ],
                [("Tcl/Tk license.terms", tk_license.read_text("utf-8", errors="replace"))],
            )
        )

    openssl_version_match = re.search(r"OpenSSL\s+(\d+\.\d+\.\d+)", ssl.OPENSSL_VERSION)
    openssl_version = openssl_version_match.group(1) if openssl_version_match else ssl.OPENSSL_VERSION
    sections.append(
        _section(
            f"OpenSSL {openssl_version}",
            [
                "License: Apache-2.0",
                f"Source: https://github.com/openssl/openssl/releases/tag/openssl-{openssl_version}",
            ],
            [("Apache License 2.0", apache_license)],
        )
    )

    sections.append(
        _section(
            f"SQLite {sqlite3.sqlite_version}",
            [
                "License: Public Domain",
                "Source and copyright statement: https://www.sqlite.org/copyright.html",
            ],
            [],
        )
    )
    return sections


def build_notices() -> str:
    distributions = _runtime_distributions()
    dependency_sections: list[str] = []
    mpl_sources: list[str] = []
    apache_license = ""

    for distribution in distributions:
        name = distribution.metadata["Name"]
        expression = _license_expression(distribution)
        license_files = _license_files(distribution)
        if "MPL" in expression.upper():
            mpl_sources.append(f"- {name} {distribution.version}: {_pypi_url(distribution)}")
        if not apache_license and "APACHE-2.0" in expression.upper() and license_files:
            apache_license = license_files[0][1]

        dependency_sections.append(
            _section(
                f"{name} {distribution.version}",
                [
                    f"License: {expression}",
                    f"Exact source distribution: {_pypi_url(distribution)}",
                    f"Upstream: {_upstream_url(distribution)}",
                ],
                license_files,
            )
        )

    if not apache_license:
        raise RuntimeError("No installed Apache-2.0 dependency supplied the OpenSSL license text")

    header = [
        "HF GGUF Downloader - Third-Party Notices",
        "",
        "This file covers third-party components redistributed with the Windows executable.",
        "HF GGUF Downloader itself is licensed under the MIT License; see LICENSE.txt.",
        "Package versions are generated from the runtime dependency closure installed from uv.lock.",
        "",
        "Source code availability for components covered by the Mozilla Public License 2.0:",
        *mpl_sources,
        "",
        "The links above lead to the exact-version source distributions. The remaining sections",
        "reproduce the license and notice files supplied by each installed distribution.",
        "",
    ]

    return "\n".join(header + _python_runtime_sections(apache_license) + dependency_sections) + "\n"


def main() -> None:
    OUTPUT_PATH.write_text(build_notices(), encoding="utf-8", newline="\n")
    print(f"Generated {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
