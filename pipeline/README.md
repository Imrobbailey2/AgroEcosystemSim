# agroeco-pipeline

Builds cited, licensed data packs for the game: soils, weather, fertilizer
recommendations, budgets, custom-hire rates and market channels.

## How it works

```
fetch (CI, network)                         build (offline, deterministic)
SSURGO / budgets / FAWN ──► sources/extracted/<region>/ ──┐
                            + fetch-lock.json (sha256)     ├──► data/packs/<region>-v<version>.json
sources/manual/*.csv (hand-entered, cited) ────────────────┘        (validated)
```

| Path | Contents |
|---|---|
| `sources/sources.json` | Source registry: citation, URL, access date and license for every source |
| `sources/manual/` | Hand-entered tables (SL129, interim N rule, custom rates). Every row names its source and location. |
| `sources/review/needs-expert-review.json` | Items awaiting expert decisions (e.g. the corn N rule). Exported into the pack as `review_flags`. |
| `sources/regions/<region>.json` | Region settings: map units, weather station, budgets, label-to-field mapping, county map (`map`) |
| `sources/extracted/<region>/` | Written by `fetch`: SSURGO responses, budget lines with cell references, daily weather, county map extracts, lock file |

Copyrighted raw files (budget workbooks) are never committed; only extracted
values with cell references and checksums.

## County map extracts (Increment 3)

Fetch steps `city_limits`, `county_outline` and `parcel_shapes` (or `map` in the
Fetch sources workflow for all three) write `city_limits.json`,
`county_outline.json`, `parcel_shapes.json` and `map_measurements.json`.
Geometry is projected by the server to EPSG:3086 (metres) and rounded to whole
metres. Parcels keep only the shape, the DOR land-use code and the land area:
owner names, addresses, legal descriptions, parcel IDs, alternate keys and
object IDs are refused or dropped (`arcgis.py`). `map_measurements.json`
reports parcel counts under the interim eligibility rule and the estimated map
size at each simplification tolerance. See `docs/increment-3-county-map.md`.

## Commands

```bash
python -m pip install -e ".[dev]"
agroeco-pipeline fetch --region suwannee           # needs network; normally run by the "Fetch sources" workflow
agroeco-pipeline fetch --region suwannee --only city_limits county_outline parcel_shapes
agroeco-pipeline build --region suwannee           # writes data/packs/suwannee-v0.1.0.json
agroeco-pipeline build --region suwannee --check   # CI: committed pack must match a fresh build
agroeco-pipeline validate ../data/packs/suwannee-v0.1.0.json
pytest
```

## Rules enforced by `validate`

- The pack matches `schemas/datapack.schema.json`.
- Every number is covered by a `prov` object (on itself or a parent) that cites a
  registered source and a location.
- Every source has a title, URL, access date and license.
- Every `review_flag` reference points to an item in the review register.
