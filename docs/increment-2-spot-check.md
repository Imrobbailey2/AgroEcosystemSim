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

The pipeline takes the **first numeric cell to the right** of each budget
label. For rows 7 and 8, open `budgets.<tenure>.lines` in the pack, find the
label, and confirm the picked cell is the right column (for example, the
per-acre value rather than a quantity). If not, change `pick` in
`pipeline/sources/regions/suwannee.json` and rebuild.

## Results

- Checked by:
- Date:
- Overall: PASS / FAIL (list failing rows)
