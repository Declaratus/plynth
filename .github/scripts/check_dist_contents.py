"""Fail if a built distribution contains files outside the published allowlist.

The source archive and the wheel are public on PyPI, so each may carry only the
files needed to build and use plynth. Run after building:

    python .github/scripts/check_dist_contents.py dist
"""

from __future__ import annotations

import sys
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

# Paths inside the source archive, relative to its top-level folder. hatchling
# always adds the project's .gitignore, which lists only build and cache paths.
SDIST_FILES = {
    "PKG-INFO",
    "pyproject.toml",
    "README.md",
    "LICENSE",
    "CHANGELOG.md",
    ".gitignore",
}
SDIST_PREFIXES = ("plynth/",)
# Paths inside the wheel.
WHEEL_PREFIXES = ("plynth/",)


def _sdist_problems(path: Path) -> list[str]:
    problems = []
    with tarfile.open(path) as archive:
        for member in archive.getmembers():
            if member.isdir():
                continue
            parts = PurePosixPath(member.name).parts
            if len(parts) < 2:
                problems.append(f"{member.name}: outside the archive's top-level folder")
                continue
            if not member.isreg():
                problems.append(f"{member.name}: not a regular file")
                continue
            relative = "/".join(parts[1:])
            if "__pycache__" in parts or relative.endswith((".pyc", ".pyo")):
                problems.append(f"{relative}: compiled file")
                continue
            if relative in SDIST_FILES or relative.startswith(SDIST_PREFIXES):
                continue
            problems.append(relative)
    return problems


def _wheel_problems(path: Path) -> list[str]:
    problems = []
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if name.endswith("/"):
                continue
            top = name.split("/", 1)[0]
            if name.startswith(WHEEL_PREFIXES) or (
                top.startswith("plynth-") and top.endswith(".dist-info")
            ):
                continue
            problems.append(name)
    return problems


def main(argv: list[str]) -> int:
    dist = Path(argv[1] if len(argv) > 1 else "dist")
    sdists = sorted(dist.glob("*.tar.gz"))
    wheels = sorted(dist.glob("*.whl"))
    if not sdists or not wheels:
        print(f"::error::Expected a source archive and a wheel in {dist}/.")
        return 1
    failed = False
    for path, problems in [(p, _sdist_problems(p)) for p in sdists] + [
        (p, _wheel_problems(p)) for p in wheels
    ]:
        if problems:
            failed = True
            print(f"::error::{path.name} contains files outside the published allowlist:")
            for problem in problems:
                print(f"  {problem}")
        else:
            print(f"{path.name}: only allowlisted files.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
