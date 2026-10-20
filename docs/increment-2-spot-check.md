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

## Results: second pass

- Checked by:
- Date:
- Overall: PASS / FAIL (list failing rows)
