# Source files

Redistributed unmodified from ICIMOD under CC BY 4.0. Do not edit these — the pipeline treats
them as read-only, and their byte-identity to the published releases is what makes the version
diff trustworthy.

| File | Release | Published | Records |
| --- | --- | --- | --- |
| `HMAGLOFDB_v1_0_30122022.csv` | v1.0 | 2022-12-30 | 697 |
| `HMAGLOFDB_v2_0_13122023.csv` | v2.0 | 2023-12-13 | 703 |
| `HMAGLOFDB_v3_0_13122024.csv` | v3.0 | 2024-12-13 | 736 |
| `HMAGLOFDB_v4_0_13122025.csv` | v4.0 | 2025-12-13 | 766 |

All four are **cp1252 encoded**, not UTF-8. Reading them as UTF-8 raises a decode error. The
pipeline opens them with `encoding="cp1252"` and writes UTF-8 output.

Each file has the same 59 columns. The variable definitions are in the Data Description document
published alongside the dataset at https://doi.org/10.26066/RDS.1973283 — not redistributed here,
since it is a separate document rather than the data itself.

## Column notes that catch people out

- `GF_ID` is **not stable across releases**. It is reassigned every year.
- `Year_approx` is documented as INT but contains strings such as `Before 1966`, `2002-2004`,
  `1960s` and `May to August 2003`.
- `Volume`, `Lives_total`, `Livestock`, `Residential_destroyed`, `Hydropower`, `Agricultural`
  and several others contain free text and `+` markers alongside numbers.
- U+00A0 (non-breaking space) is used as an empty-cell placeholder in 17 fields.
- Eight disaggregation fields (`Injured_male`, `Displaced_female` and similar) are empty in every
  row of every release.
