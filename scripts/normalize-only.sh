#!/usr/bin/env bash
# Turn the free-text "only" input of the Fetch sources workflow into a clean
# list of pipeline steps, one per line, in the order soils, budgets, weather,
# parcels, ers, city_limits, county_outline, parcel_shapes.
#
# Forgiving on purpose: case, quotes, commas and extra spaces are ignored;
# "soil"/"budget"/"parcel" are accepted for "soils"/"budgets"/"parcels"; filler
# words such as "only", "blank", "all", "none" and "empty" are dropped. If
# nothing is left, nothing is printed, which means "run all steps".
#
# County map steps (Increment 3): "parcel_shapes" (or "shapes"), "city_limits"
# (or "cities"), "county_outline" (or "outline"); "map" selects all three.
# Underscores may be typed as spaces ("parcel shapes" is parcel_shapes, not
# parcels).
#
# An unknown word stops with a clear error that lists the valid choices.
#
# Usage: bash scripts/normalize-only.sh "<only input>"
set -euo pipefail

raw="${1:-}"
# Lower-case, then squeeze every run of non-letters into a single space.
cleaned="$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z' ' ')"
# Two-word step names (underscores became spaces above) become one word.
cleaned=" $cleaned "
cleaned="${cleaned// parcel shapes / parcelshapes }"
cleaned="${cleaned// city limits / citylimits }"
cleaned="${cleaned// county outline / countyoutline }"

want_soils=0
want_budgets=0
want_weather=0
want_parcels=0
want_ers=0
want_city_limits=0
want_county_outline=0
want_parcel_shapes=0
for word in $cleaned; do
  case "$word" in
    soil | soils) want_soils=1 ;;
    budget | budgets) want_budgets=1 ;;
    weather) want_weather=1 ;;
    parcel | parcels) want_parcels=1 ;;
    ers) want_ers=1 ;;
    citylimits | cities | city) want_city_limits=1 ;;
    countyoutline | outline) want_county_outline=1 ;;
    parcelshapes | shapes) want_parcel_shapes=1 ;;
    map) want_city_limits=1; want_county_outline=1; want_parcel_shapes=1 ;;
    only | blank | all | none | empty | and) ;;
    *)
      echo "error: '$word' is not a fetch step in only='$raw'. Leave 'only' empty to run all steps, or enter any of: soils budgets weather parcels ers city_limits county_outline parcel_shapes (or map for the last three)" >&2
      exit 2
      ;;
  esac
done

if [ "$want_soils" = 1 ]; then echo soils; fi
if [ "$want_budgets" = 1 ]; then echo budgets; fi
if [ "$want_weather" = 1 ]; then echo weather; fi
if [ "$want_parcels" = 1 ]; then echo parcels; fi
if [ "$want_ers" = 1 ]; then echo ers; fi
if [ "$want_city_limits" = 1 ]; then echo city_limits; fi
if [ "$want_county_outline" = 1 ]; then echo county_outline; fi
if [ "$want_parcel_shapes" = 1 ]; then echo parcel_shapes; fi
