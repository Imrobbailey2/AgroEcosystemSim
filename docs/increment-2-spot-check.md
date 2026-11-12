# Increment 2: data pack spot-check

Goal: confirm that 10 values in `data/packs/suwannee-v0.1.0.json` match their
original sources. Each data-pack record has a `prov` object naming the source
(`sources`) and where in it the value came from (`loc`). Budget values give the
exact workbook cell (for example `Budget!F12`).

Open the source, find the location, and compare. Mark each row pass or fail.

| # | Value in the pack | Where to find it in the pack | Source and location | Expected | Pass/fail |
|---|---|---|---|---|---|
| 1 | P rating Low upper limit | `soil_test.ratings` (P, Low) | SL129 Table 1 | ≤25 mg/kg | |
| 2 | K rating High lower limit | `soil_test.ratings` (K, High) | SL129 Table 1 | >60 mg/kg | |
| 3 | N for irrigated corn, 30,000 plants/acre | `crops[0].fertilizer_by_population` | SL129 Table 2, crop code 5 | 240 lb N/A | |
| 4 | P₂O₅ at Medium soil P, 25,000 plants/acre | `crops[0].fertilizer_by_population` | SL129 Table 2, crop code 5 | 70 lb/A | |
| 5 | Interim N at 200 bu/ac | `crops[0].n_rules.rules[1].table` | UF/IFAS corn page, Table 2 | 274 lb N/ac | |
| 6 | Combine corn custom rate | `custom_operations` (`combine_corn`) | 2024 Georgia Custom Rate Survey, Harvest Operations | $58.50/acre average | |
| 7 | Benchmark yield, owned land | `tenure_options` (`owned`) | 2026 SV CT Owned budget, cell in `prov.loc` | (from workbook) | |
| 8 | Land rent, rented land | `tenure_options` (`rented`) | 2026 SV CT Rented budget, cell in `prov.loc` | (from workbook) | |
| 9 | Field 1 dominant component and top-layer field capacity | `soil_units[0]` | Web Soil Survey, FL121, map unit in `prov.loc` | (from SSURGO) | |
| 10 | Driest-season April–August rainfall | `weather_years` (role `dry`) | FAWN Live Oak daily rain, same dates | (sum of daily rain) | |

## Also check (budget cell mapping)

Each game value is read from a **named workbook column** (`budget_fields.<name>.col`
in `pipeline/sources/regions/suwannee.json`). For rows 7 and 8, open
`budgets.<tenure>.lines` in the pack, find the label, and confirm the cell in
`prov.loc` is the per-acre (or per-bushel) value, not a whole-farm total.
Validation also rejects any per-acre cost outside 0 to revenue per acre.

## Results: first pass (data branch `data/fetch-39487912435`, 2026-10-20)

| # | Result | Notes |
|---|---|---|
| 1 | PASS | SL129 Table 1: P Low ≤25 mg/kg |
| 2 | PASS | SL129 Table 1: K High >60 mg/kg |
| 3 | PASS | SL129 Table 2, code 5, 30,000 plants/acre: 240 lb N/A |
| 4 | PASS | SL129 Table 2, code 5, 25,000 plants/acre, Medium P: 70 lb P₂O₅/A |
| 5 | PASS | UF/IFAS corn page Table 2: 200 bu/ac → 274 lb N/ac |
| 6 | PASS | Georgia 2024 survey, Combine Corn: $58.50 average ($55.00 median, $40.00–$90.00) |
| 7 | PASS | Owned budget `Marketing!C7` = 205 bu/A |
| 8 | **FAIL** | Rented budget: pack used `FieldDetails!D19` = $40,000 (whole-farm total) as $/acre; per-acre value is `FieldDetails!E19` = $285.71. Fixed by picking named columns; re-check after the next fetch. |
| 9 | PASS | FL121 mukey 1023328: dominant component Blanton 42%, moderately well drained; top layer 0–13 cm, FC 7.9%, WP 2.0% (checked against the SDA extract) |
| 10 | PENDING | Re-check after the next fetch using the dry year and season rainfall in the pack |

Decisions recorded on 2026-10-20:

- The market channel pays the **net farm-gate price** (`Marketing!C27` = $4.78/bu) rather than
  the gross delivered price (`Marketing!C8` = $5.20/bu). Hauling is already deducted, so it is
  not charged again.
- Owned land will carry property tax, utilities and other ownership costs, and will gain value
  over time. The sources still need approval; the decision is tracked in the review register.
  (Deferred to a later increment on 2026-11-02 by project-owner decision — see the review
  register item `owned-land-costs`.)

Decision recorded on 2026-11-05 (C27 vs. C39, option C):

- The Marketing sheet (owned and rented identical) gives: gross revenue $1,066.00/A
  (205 bu × $5.20); minus buyer drying fees $24.60/A ($0.12/bu) and buying-point hauling
  $61.50/A ($0.30/bu) = **net farm-gate sales revenue `C27` $4.78/bu ($979.90/A)**; minus the
  **crop insurance premium, Revenue Protection 75%, $12.20/A ($0.06/bu)** = total net farm-gate
  crop revenue `C39` $4.72/bu ($967.70/A). Additional crop revenues are $0.
- The market keeps paying `C27`. The premium is a separate, cited cost
  (`crop_insurance_options`, bought by default, proceeds not modelled), so insurance can become a
  player decision. Buyer drying and hauling are recorded under the market channel's
  `included_deductions` for reference only and are never charged again.
- Validation now checks yield × price − premium = the budget's `Marketing!D39` (±$0.01/A). The
  review register item `budget-cell-mapping` is resolved.

## Second-pass re-check of rows 8 and 10 (2026-11-02, row 8 completed 2026-11-04)

> **Second-pass sign-off is pending the project owner's signature.** The two
> rows below are re-checked against the pack; the sign-off block at the end is
> intentionally left blank for the project owner to complete.

| # | Result | Notes |
|---|---|---|
| 10 | PASS | Dry year is `weather_years` role `dry` = station 170, 2010. Its `season` block (April 1 – August 31) reports `rain_mm` = 442.7 mm, the sum of the daily `rain_mm` over those dates. Matches FAWN Live Oak daily rain for the same window. |
| 8 | PASS | Pack regenerated on `fix-budget-columns` (commits `1298b3f`, `87a8b74`; CI green on `87a8b74`). `tenure_options[rented].land_rent_usd_ac` = 285.7142857142857 at `FieldDetails!E19` (source `svaec-corn-2026-ct-rented`), no longer the whole-farm total `FieldDetails!D19` = $40,000. Within 0 to revenue per acre (205 bu/A × $4.78/bu = $979.90/A). Related changes confirmed in the same pack: benchmark and market price = $4.78/bu at `Marketing!C27`, gross price $5.20/bu at `Marketing!C8`, `price_basis` = `net_farm_gate`, no separate hauling charge. |

## Results: second pass

- Checked by:ImRobbailey2
- Date:11-6-2026
- Overall: PASS 

## Increment 2b: owned-land costs and land appreciation (rows 11–18)

Pack built by PR #12 and rebuilt by Fetch sources run 43239622406 (pack commit
`67558b8`, CI green). All values below are in `tenure_options` (`owned`). The
"Pack value" column was read from the committed pack; confirm each against the
original source and mark pass or fail. Option C (2026-11-09): property tax +
property insurance must equal the owned budget's "Property tax and insurance".

| # | Value in the pack | Where to find it in the pack | Source and location | Pack value | Pass/fail |
|---|---|---|---|---|---|
| 11 | Median agricultural-use assessed value, Suwannee cropland | `property_tax_basis.use_value_usd_ac` | Florida Statewide Parcels (FGIO), CO_NO 71, DOR_UC 051–053, 2026 roll; `pipeline/sources/extracted/suwannee/parcels_summary.json` (`classified_use_assessed_usd_ac.median`, 431 parcels) | $278.63/A | |
| 12 | FY2026-27 total millage | `property_tax_basis.millage`, `total_mills` | County 8.8000 (BOCC final budget hearing 2026-09-21); School Board 5.405 (Resolution SCSB 2027-04R); SRWMD 0.2695 (Resolution 2026-14); total vs. Suwannee County Property Appraiser Tax Rates page | 14.4745 mills | |
| 13 | Property tax | `property_tax_usd_ac` | Arithmetic: $278.63 × 14.4745 / 1,000 = $4.0330, rounded to cents | $4.03/A/yr | |
| 14 | Owned budget "Property tax and insurance" (per acre, not whole-farm) | `budget_property_tax_and_insurance_usd_ac` | 2026 SV CT Owned budget, `FieldDetails!E21` (whole-farm total `D21` = $1,400 on 140 acres) | $10.00/A | |
| 15 | Property insurance (option C remainder) | `property_insurance_usd_ac` | $10.00 (row 14) − $4.03 (row 13); not negative | $5.97/A/yr | |
| 16 | Maintenance/upkeep | `upkeep_usd_ac` | USDA ERS Commodity Costs and Returns, `CornCostReturn.csv`: Corn, Southern Seaboard, "General farm overhead", dollars per planted acre, 2024 | $23.96/A/yr | |
| 17 | Basic owned-land cost | `owned_land_cost_usd_ac` | Sum of rows 13, 15, 16: $4.03 + $5.97 + $23.96 | $33.96/A/yr | |
| 18 | Land value series and appreciation rate | `land_appreciation.series`, `land_appreciation.rate_per_yr` | USDA NASS Land Values 2026 Summary (July 2026), Cropland Average Value per Acre, Florida: 2022 $8,340; 2023 $9,290; 2024 $10,170; 2025 $10,550; 2026 $11,100. Rate = (11,100 / 8,340)^(1/4) − 1 | 0.074086 (7.41%/yr) | |

Also check: the `rented` tenure option carries none of these fields, and each
`*_usd_ac` value has a `prov` naming registered sources (validation enforces
both; CI is green on `67558b8`).

### Results: Increment 2b

- Checked by:
- Date:
- Overall:
