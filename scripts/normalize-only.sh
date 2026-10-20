#!/usr/bin/env bash
# Turn the free-text "only" input of the Fetch sources workflow into a clean
# list of pipeline steps, one per line, in the order soils, budgets, weather.
#
# Forgiving on purpose: case, quotes, commas and extra spaces are ignored;
# "soil"/"budget" are accepted for "soils"/"budgets"; filler words such as
# "only", "blank", "all", "none" and "empty" are dropped. If nothing is left,
# nothing is printed, which means "run all steps".
#
# An unknown word stops with a clear error that lists the valid choices.
#
# Usage: bash scripts/normalize-only.sh "<only input>"
set -euo pipefail

raw="${1:-}"
# Lower-case, then squeeze every run of non-letters into a single space.
cleaned="$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z' ' ')"

want_soils=0
want_budgets=0
want_weather=0
for word in $cleaned; do
  case "$word" in
    soil | soils) want_soils=1 ;;
    budget | budgets) want_budgets=1 ;;
    weather) want_weather=1 ;;
    only | blank | all | none | empty | and) ;;
    *)
      echo "error: '$word' is not a fetch step in only='$raw'. Leave 'only' empty to run all steps, or enter any of: soils budgets weather" >&2
      exit 2
      ;;
  esac
done

if [ "$want_soils" = 1 ]; then echo soils; fi
if [ "$want_budgets" = 1 ]; then echo budgets; fi
if [ "$want_weather" = 1 ]; then echo weather; fi
