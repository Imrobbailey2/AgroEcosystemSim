#!/usr/bin/env python3
"""Fail if any tracked file matches a pattern in ``.forbidden-paths``.

This is the CI guard that keeps UF validation data and private calibration
data out of the public repository.

Usage::

    python scripts/check_forbidden.py            # check git-tracked files
    python scripts/check_forbidden.py PATH ...   # check the given paths only

Exit codes: 0 = clean, 1 = forbidden files found, 2 = configuration error.
"""

from __future__ import annotations

import fnmatch
import os
import subprocess
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PATTERN_FILE = REPO_ROOT / ".forbidden-paths"
SKIP_DIRS = {".git", "node_modules", "dist", ".venv", "__pycache__"}


def load_patterns(pattern_file: Path = PATTERN_FILE) -> list[str]:
    """Read glob patterns, ignoring blank lines and comments."""
    try:
        text = pattern_file.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"error: cannot read {pattern_file}: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    patterns = [
        line.strip().lower()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    if not patterns:
        print(f"error: no patterns found in {pattern_file}", file=sys.stderr)
        raise SystemExit(2)
    return patterns


def tracked_files(root: Path = REPO_ROOT) -> list[str]:
    """Return git-tracked files, or walk the tree if git is unavailable."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=root,
            check=True,
            capture_output=True,
        ).stdout.decode("utf-8")
        return [p for p in out.split("\0") if p]
    except (OSError, subprocess.CalledProcessError):
        files: list[str] = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for name in filenames:
                rel = Path(dirpath, name).relative_to(root)
                files.append(rel.as_posix())
        return files


def find_violations(
    paths: Iterable[str], patterns: Sequence[str]
) -> list[tuple[str, str]]:
    """Return (path, pattern) pairs for every path matching a forbidden pattern."""
    hits: list[tuple[str, str]] = []
    for path in paths:
        candidate = "/" + path.replace("\\", "/").lstrip("/").lower()
        for pattern in patterns:
            if fnmatch.fnmatchcase(candidate, pattern):
                hits.append((path, pattern))
                break
    return hits


def main(argv: Sequence[str] | None = None) -> int:
    """Run the guard and return a process exit code."""
    args = list(sys.argv[1:] if argv is None else argv)
    patterns = load_patterns()
    paths = args or tracked_files()
    hits = find_violations(paths, patterns)
    if hits:
        print("FORBIDDEN FILES DETECTED (UF validation / private data):", file=sys.stderr)
        for path, pattern in hits:
            print(f"  {path}   (matches {pattern!r})", file=sys.stderr)
        print(
            "\nRemove these files from the commit and from history. "
            "See CONTRIBUTING.md, section 'Data rules'.",
            file=sys.stderr,
        )
        return 1
    print(f"Data guard OK: {len(paths)} files checked against {len(patterns)} patterns.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
