# Increment 2b: owned-land costs and land appreciation (design note)

Status: **decisions recorded 2026-11-06 and 2026-11-07; fetch steps `parcels`
and `ers` added; sources registered; cost lines not yet built.**
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
| Property tax | Median agricultural-use (greenbelt) assessed land value per acre, Suwannee County cropland (DOR use codes 051-053), from the Florida Statewide Parcels layer (fetch step `parcels`) x 14.4745 mills (FY2026-27) = **$4.03/A/yr** | `owned-land-use-value` |
| Property insurance | USDA ERS Commodity Costs and Returns, corn, Southern Seaboard, "Taxes and insurance", latest actual year (fetch step `ers`; flagged upper estimate) | `owned-land-insurance-proxy` |
| Maintenance/upkeep | USDA ERS, corn, Southern Seaboard, "General farm overhead" (fetch step `ers`; only if the workbook scan finds no overlap) | `owned-land-upkeep-proxy` |
| Basic average | Sum of the three lines | `owned-land-costs` |

### Millage, FY2026-27, unincorporated Suwannee County

The 2026 tax roll (the parcel values used here) is taxed at the FY2026-27
rates (project-owner decision 2026-11-07).

| Taxing authority | Mills | Adoption document | Source id |
|---|---|---|---|
| Suwannee County Board of County Commissioners | 8.8000 | Final budget hearing 2026-09-21 (rolled-back rate 8.3590) | `suwannee-bocc-millage-fy2027` |
| Suwannee County School Board | 5.405 (3.157 + 0.748 + 1.500) | Final hearing 2026-09-08, Resolution SCSB 2027-04R | `suwannee-school-board-millage-fy2027` |
| Suwannee River Water Management District | 0.2695 | Resolution 2026-14, final hearing 2026-09-21 | `srwmd-millage-fy2027` |
| **Total** | **14.4745** | | |

The total matches the Property Appraiser's Tax Rates page. Superseded
FY2025-26 rates: 8.8000 + 5.415 + 0.2812 = 14.4962. The signed SRWMD
resolution has not been seen (staff recommendation and the Alachua County
Property Appraiser's 2026 rate table both give 0.2695).

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
  $234.99.
- Decided 2026-11-07: use all 431 parcels with no municipal filter (the
  taxing-authority field is `CO` for every parcel, so Live Oak and Branford
  cannot be separated) and exclude improved agricultural (050) parcels.
  `JV_CLASS_USE` (median $2,000/A, flat) is not used. If the automated fetch
  fails, the fallback is a one-time manual export from the Property
  Appraiser's Download Manager.

### ERS cost lines (automated fetch step `ers`)

- Source: USDA ERS Commodity Costs and Returns, corn CSV (updated 10/1/2026;
  next update 5/3/2027), `usda-ers-ccr-corn`.
- Filter: Commodity `Corn`, Region `Southern Seaboard`, Units `dollars per
  planted acre`, Items `Taxes and insurance` and `General farm overhead`; the
  last 5 actual years are kept (forecast rows such as `2026F` are skipped).
  Output: `ers_costs.json`. If a name does not match, the fetch stops and
  lists the regions or items that do exist.
- For scale only: the ERS 2026 U.S. forecast is $21.46 (taxes and insurance)
  and $26.03 (general farm overhead) per planted acre.

## Land appreciation

USDA NASS Land Values 2026 Summary (released July 31, 2026), Florida cropland
average value per acre, entered by hand (`usda-nass-land-values-2026`):

| 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|
| $8,340 | $9,290 | $10,170 | $10,550 | $11,100 |

Compound average annual growth 2022-2026: **7.41%/yr**. Year-on-year: +11.4%,
+9.5%, +3.7%, +5.2%, so the average is on the high side of recent years.
State-level only; NASS publishes no county value. The game applies
appreciation in Increment 3.

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
