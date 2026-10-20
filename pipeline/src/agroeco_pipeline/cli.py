"""Command-line entry point: ``agroeco-pipeline build --region <name>``.

Increment 0 provides only the command shape; the build itself arrives in
Increment 2 (Data pack v0).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from agroeco_pipeline import __version__

KNOWN_REGIONS = ("suwannee",)
EXIT_NOT_IMPLEMENTED = 3


def build_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(
        prog="agroeco-pipeline",
        description="Build cited data packs for the farm simulator.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="Build a region data pack.")
    build.add_argument("--region", required=True, choices=KNOWN_REGIONS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments and dispatch. Returns a process exit code."""
    args = build_parser().parse_args(argv)
    if args.command == "build":
        print(
            f"build --region {args.region}: not implemented yet (Increment 2).",
            file=sys.stderr,
        )
        return EXIT_NOT_IMPLEMENTED
    return 1  # pragma: no cover - argparse enforces a subcommand


if __name__ == "__main__":
    sys.exit(main())
