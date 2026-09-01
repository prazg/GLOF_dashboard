# Inventory of glacial lake outburst floods (GLOFs) in High Mountain Asia 2022-2025 | HMAGLOFDB review

An interactive review of the **HMAGLOFDB**, ICIMOD's inventory of glacial lake outburst floods
(GLOFs) in High Mountain Asia: across the four annual releases from 2022 to 2025.

**Dashboard: https://prazg.github.io/GLOF_dashboard/**

---
## Why this exists

HMAGLOFDB is the most complete GLOF inventory available for the region and is published openly under
CC BY 4.0. Using it well takes some care: several fields documented as integers contain prose, the
event identifier is reassigned at every release, and roughly a fifth of events carry no date. This
repository does not correct the database — that is ICIMOD's to do — it makes those properties
visible before they reach an analysis, and preserves every original value.

## What the review found

| Finding | Why it matters |
| --- | --- |
| `GF_ID` is reassigned at every release | Of the 697 IDs shared by v1.0 and v4.0, only 16% point to a record with the same lake coordinate. A stored reference to a `GF_ID` silently points at a different flood after an update. |
| One record genuinely withdrawn in four releases | Nine of the ten records without an exact match resolve to the same lake with a corrected date, coordinate or name. The exception is Bhairav Taal, Nepal, dated 5 July 2024 in v3.0, with no record within 2 km in v4.0. |
| Free text in integer fields | `Hydropower` holds `"1200 Teesta III, 510 Teesta V, 500 Teesta VI"`; `Residential_damaged` holds `"13 houses fully damaged; 10 partially damaged"`. Summing these naively either errors or drops them. |
| Non-breaking spaces as empty-cell placeholders | U+00A0 appears in 17 fields. Those cells look populated to a parser. |
| 766 records cover 385 distinct lakes | 450 records are flagged as repeat events; Merzbacher alone contributes 85. Treating rows as independent events roughly doubles the apparent number of hazard sites. |
| 19% of events have no year, 87% no identified trigger, 96% no casualty figure | Any rate or proportion has to state which denominator it used. |

The fatality total in the cleaned file sums to 8,996, matching the figure in the v4.0 metadata
abstract. Two events supply 89% of it.

## Caveats

- The "date or name refined" verdicts in the version diff are **inferred here** from a 2 km spatial
  match plus a year comparison. They are not published by ICIMOD and are leads to check, not
  conclusions.
- No changelog accompanies the releases, so there is no independent confirmation of what ICIMOD
  intended to change between versions.
- The rise in events per decade tracks observation capacity as much as hazard. The database cannot
  separate a real increase in flood frequency from an increase in detection, and does not claim to.
- Casualty counts are lower bounds. Entries carrying `+` mean "at least this many"; the cleaned file
  moves that marker into its own `_is_minimum` column so it survives aggregation.

## Repository layout

```
index.html                 generated dashboard, served by GitHub Pages
src/build_glofdb.py        the whole pipeline: clean, check, diff, render
src/template.html          dashboard markup with a /*__DATA__*/ injection point
data/raw/                  the four HMAGLOFDB releases exactly as published (cp1252)
data/processed/            everything the pipeline produces
  HMAGLOFDB_v4_clean.csv     766 rows x 81 columns, UTF-8
  qc_report.json             17 findings, completeness table, transformation log
  version_diff.json          per-release added, unmatched and edited records
  glof_payload.json          aggregates inlined into index.html
```

## Rebuilding

```bash
pip install -r requirements.txt
python src/build_glofdb.py
```

Roughly two seconds. It rewrites `data/processed/` and `index.html`. Nothing under `data/raw/` is
ever modified.

## When v5.0 is released

1. Drop the new CSV into `data/raw/`.
2. Add one line to the `VERSIONS` dict at the top of `src/build_glofdb.py`:
   ```python
   "v5.0": ("HMAGLOFDB_v5_0_DDMMYYYY.csv", "2026-12-13"),
   ```
3. Rerun. The diff chain, the growth chart and the release-by-release tab extend on their own; the
   cleaning step always targets the last entry in the dict.

If the schema changes, the QC step will flag new field names as newly empty rather than failing
silently — check the completeness table after any update.

## What the cleaning does

Reversible repairs only. No row is dropped and no original string is lost.

- Non-breaking and zero-width spaces removed, whitespace collapsed, blanks set to `NA`
- Degree symbols stripped from coordinates so all 766 events parse as floats
- Free text in numeric fields moved to a parallel `<field>_note` column, numeric set to `NA`
- `+` split into a boolean `<field>_is_minimum` column
- `year_best` derived from `Year_exact` first, then parsed from text forms in `Year_approx`
  (`"Before 1966"`, `"2002-2004"`, `"1960s"`), with the assumption recorded in `year_precision`
- `event_date` built where day, month and year are all known
- `Driver_GLOF` and `Mechanism` split on both `;` and `,` into normalised `_terms` lists
- `"Unnamed"` and `"Unknown"` flagged in `<field>_is_placeholder`, original text kept

The full list, with row counts, is in `data/processed/qc_report.json` and on the dashboard's data
quality tab.

## Data source and attribution

ICIMOD (2025). *GLOF database of High Mountain Asia* [Data set]. International Centre for Integrated
Mountain Development. https://doi.org/10.26066/RDS.1973283 — licensed CC BY 4.0.

The files in `data/raw/` are redistributed unchanged under that licence. `data/processed/` contains
derived works, also CC BY 4.0. The code is MIT. See `LICENSE` and `LICENSE-DATA.md`.

This repository is an independent review and is not affiliated with or endorsed by ICIMOD.

