# Increment 2b: owned-land costs and land appreciation (design note)

Status: **decisions recorded 2026-11-06; automated parcel fetch (step
`parcels`) added 2026-11-07; cost lines not yet built.**
Review register items: `owned-land-costs`, `owned-land-use-value`,
`owned-land-insurance-proxy`, `owned-land-upkeep-proxy`,
`land-appreciation-method`, `advanced-mode-scope`
(`pipeline/sources/review/needs-expert-review.json`).

## Game modes

| | Basic | Advanced |
|---|---|---|
| Field work | Hired custom operations only | Custom hire, or owned machinery, hired workers, farm trucks, buildings (later increments) |
| Owned-land cost | One average, $/acre/year | Three lines: property tax, property insurance, maintenance/upkeep |
| Crop insurance | Revenue Protection 75% (`rp-75`, $12.20/A, `Marketing!D30`) always bought | Player choice (needs payouts modelled first) |

Both modes read the same data pack. The Basic average is the sum of the
Advanced lines, so the two can never disagree.

## Owned-land cost lines

| Line | Formula / source | Review item |
|---|---|---|
| Property tax | Median agricultural-use (greenbelt) assessed land value per acre, unincorporated Suwannee County cropland (DOR use codes 051-053), from the Florida Statewide Parcels layer (fetch step `parcels`) x 14.4962 mills | `owned-land-use-value` |
| Property insurance | USDA ERS Commodity Costs and Returns, corn, Southern Seaboard, "Taxes and insurance", latest actual year (flagged upper estimate) | `owned-land-insurance-proxy` |
| Maintenance/upkeep | USDA ERS, corn, Southern Seaboard, "General farm overhead" (only if the workbook scan finds no overlap) | `owned-land-upkeep-proxy` |
| Basic average | Sum of the three lines | `owned-land-costs` |

### Millage, FY2025-26, unincorporated Suwannee County

| Taxing authority | Mills | Adoption document |
|---|---|---|
| Suwannee County Board of County Commissioners | 8.8000 | Final millage adopted 2025-09-22 |
| Suwannee County School Board | 5.415 (3.167 + 0.748 + 1.500) | Final millage hearing 2025-09-09 |
| Suwannee River Water Management District | 0.2812 | Resolution 2025-11 |
| **Total** | **14.4962** | |

The Property Appraiser's Tax Rates page shows 14.4745 (schools 5.4050,
SRWMD 0.2695). The pack cites the adoption documents and records the
difference.

### Parcel data (automated fetch step `parcels`)

- Source: **Florida Statewide Parcels** (State of Florida Geographic
  Information Office), the Florida DOR parcel GIS joined with the real property
  assessment roll (NAL) that the Suwannee County Property Appraiser submits to
  the Department. Queried through its public ArcGIS REST API; no manual export.
- Filter: `CO_NO = 71` (Suwannee) and `DOR_UC` 051-053 (cropland, soil
  capability Class I-III, per the 2025 DOR NAL/SDF/NAP User's Guide).
- Value per acre = `AV_CLASS_USE` (assessed value of the agriculturally
  classified portion) / parcel acres (`LND_SQFOOT` / 43,560). Parcel acres
  include any non-classified portion (e.g. a homesite), so values are
  conservative. Median, 25th and 75th percentiles, counts by use code and by
  taxing authority, and assessment year go to `parcels_summary.json`.
- Privacy: only allow-listed value and land-use fields are requested. Owner
  names, mailing addresses, parcel IDs and geometry are never downloaded; the
  code refuses to request `OWN_*`, `FIDU_*`, `PHY_ADDR*`, `PARCEL_ID`,
  `S_LEGAL`, `ALT_KEY` fields. Only aggregates are committed; the sha256 of
  every query page is in `fetch-lock.json`.
- First fetch (2026-11-07, run 42384231645, 2026 roll): 431 parcels, median
  **$278.63/A** (p25 $235.00, p75 $285.00; min $41.81, max $1,253.00). By
  code: 051 1 parcel $277.53; 052 240 parcels $285.00; 053 190 parcels
  $234.99. At 14.4962 mills: about $4.04/A/yr property tax.
- Decided 2026-11-07: use all 431 parcels with no municipal filter (the
  taxing-authority field is `CO` for every parcel, so Live Oak and Branford
  cannot be separated) and exclude improved agricultural (050) parcels.
  `JV_CLASS_USE` (median $2,000/A, flat) is not used. If the automated fetch
  fails, the fallback is a one-time manual export from the Property
  Appraiser's Download Manager.

## Land appreciation

USDA NASS Land Values, Florida cropland average value per acre, 2022-2026.
Store the series and the average annual growth rate (2025 $10,550/A, 2026
$11,100/A, +5.2%). State-level only; NASS publishes no county value. The game
applies appreciation in Increment 3.

## Double-counting risks

1. **Machinery insurance in Basic mode.** The ERS "Taxes and insurance" line
   includes machinery insurance, but Basic mode uses custom hire, whose rates
   already include the contractor's costs. Flagged; replace with a
   farm-liability-only source when found.
2. **Overhead already in the budget.** Before adding ERS general farm overhead,
   scan the SVAEC owned workbook for overhead, utilities, maintenance, tax or
   insurance lines, and the `FieldOperations` fixed costs. Stop and report any
   overlap.
3. **Real-estate tax.** Under the current ERS method, "Taxes and insurance"
   excludes real-estate tax, so it does not overlap the property-tax line.

## Increment 2b acceptance criteria

1. Every new value cites a registered source in `pipeline/sources/sources.json`
   with a locator (`provenance_problems` passes).
2. Owned tenure option carries the three cost lines and the Basic total; the
   total equals the sum to within $0.01/A (new validation check).
3. Each owned-land cost is within 0 to revenue per acre (existing plausibility
   rule for `*_usd_ac`).
4. Land appreciation series and rate are in the pack with provenance.
5. Workbook overlap scan result is recorded in the review register.
6. Tests cover the sum check, the parcel summary (including dropped personal
   columns) and the appreciation rate.
7. The pack rebuilds byte-identically in CI; spot-check rows added for the new
   values and signed by the project owner.

## Approved order of work

1. Increment 2b (this note): owned-land costs and land appreciation.
2. Increment 3: UI-free engine in `game/src/engine/`, Basic mode end to end,
   with a basic/advanced mode switch from the start.
3. Advanced-mode requirements: owned machinery, labor, trucks, buildings,
   financing, crop insurance with payouts.
4. Increments 4+: Advanced data and engine work, starting with machinery.
