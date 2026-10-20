#!/usr/bin/env bash
# Run a command; if it fails, surface its "error:" line as a GitHub Actions
# annotation so the cause appears on the run summary page.
#
#   bash scripts/annotate-errors.sh <command> [args...]
set -uo pipefail

if [ "$#" -eq 0 ]; then
  echo "usage: annotate-errors.sh <command> [args...]" >&2
  exit 64
fi

log="$(mktemp)"
trap 'rm -f "$log"' EXIT

"$@" 2> >(tee "$log" >&2)
status=$?
wait  # let tee finish writing the log

if [ "$status" -ne 0 ]; then
  msg="$(grep -m1 '^error:' "$log" || tail -n 1 "$log" || true)"
  [ -n "$msg" ] || msg="command failed with exit code $status"
  # Escape characters GitHub workflow commands treat specially.
  msg="${msg//'%'/'%25'}"
  msg="${msg//$'\r'/'%0D'}"
  msg="${msg//$'\n'/'%0A'}"
  echo "::error title=$1 failed (exit $status)::$msg"
fi
exit "$status"
