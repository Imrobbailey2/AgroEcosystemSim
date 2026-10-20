"""Command-line entry point.

    agroeco-pipeline fetch --region suwannee [--only soils budgets weather]
    agroeco-pipeline build --region suwannee [--out PATH] [--check]
    agroeco-pipeline validate PATH
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from agroeco_pipeline import __version__
from agroeco_pipeline.common import PipelineError, packs_dir

KNOWN_REGIONS = ("suwannee",)


def build_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(
        prog="agroeco-pipeline",
        description="Build cited data packs for the farm simulator.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    fetch = sub.add_parser("fetch", help="Download sources and write committed extracts (needs network).")
    fetch.add_argument("--region", required=True, choices=KNOWN_REGIONS)
    fetch.add_argument("--only", nargs="+", choices=["soils", "budgets", "weather"])

    build = sub.add_parser("build", help="Build and validate a region data pack (offline).")
    build.add_argument("--region", required=True, choices=KNOWN_REGIONS)
    build.add_argument("--out", type=Path, help="Output path (default: data/packs/<region>-v<version>.json)")
    build.add_argument("--check", action="store_true",
                       help="Fail if the committed pack differs from a fresh build.")

    val = sub.add_parser("validate", help="Validate an existing data pack file.")
    val.add_argument("path", type=Path)
    return parser


def _cmd_build(args: argparse.Namespace) -> int:
    from agroeco_pipeline.build import run_build

    if not args.check:
        path = run_build(args.region, args.out)
        print(f"Built {path}")
        return 0
    committed = args.out or next(iter(sorted(packs_dir().glob(f"{args.region}-v*.json"))), None)
    if committed is None or not committed.exists():
        print(f"No committed pack for {args.region} to compare.", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        fresh = run_build(args.region, Path(tmp) / "pack.json")
        if fresh.read_bytes() != committed.read_bytes():
            print(f"{committed} is out of date; run `agroeco-pipeline build --region {args.region}`.",
                  file=sys.stderr)
            return 1
    print(f"{committed} matches a fresh build.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments and dispatch. Returns a process exit code."""
    args = build_parser().parse_args(argv)
    try:
        if args.command == "fetch":
            from agroeco_pipeline.fetch import run_fetch

            out = run_fetch(args.region, args.only)
            print(f"Wrote extracts to {out}")
            return 0
        if args.command == "build":
            return _cmd_build(args)
        from agroeco_pipeline.validate import validate_pack

        pack = json.loads(args.path.read_text(encoding="utf-8"))
        problems = validate_pack(pack)
        for p in problems:
            print(p, file=sys.stderr)
        print(f"{args.path}: {'OK' if not problems else f'{len(problems)} problem(s)'}")
        return 1 if problems else 0
    except PipelineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
