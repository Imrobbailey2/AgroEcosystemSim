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
| `sources/regions/<region>.json` | Region settings: map units, weather station, budgets, label-to-field mapping |
| `sources/extracted/<region>/` | Written by `fetch`: SSURGO responses, budget lines with cell references, daily weather, lock file |

Copyrighted raw files (budget workbooks) are never committed; only extracted
values with cell references and checksums.

## Commands

```bash
python -m pip install -e ".[dev]"
agroeco-pipeline fetch --region suwannee           # needs network; normally run by the "Fetch sources" workflow
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
