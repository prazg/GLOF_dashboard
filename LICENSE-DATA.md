# Licence for the data in this repository

The MIT licence in `LICENSE` covers the code only — `src/build_glofdb.py` and
`src/template.html`. Everything under `data/` is covered by this file instead.

## Source data — `data/raw/`

The four HMAGLOFDB release files are redistributed here **unmodified**, byte for byte as
published, including their original cp1252 encoding.

> ICIMOD (2025). *GLOF database of High Mountain Asia* [Data set]. International Centre for
> Integrated Mountain Development. https://doi.org/10.26066/RDS.1973283

Licensed under **Creative Commons Attribution 4.0 International (CC BY 4.0)**:
https://creativecommons.org/licenses/by/4.0/

You may share and adapt these files, including commercially, provided you give appropriate
credit, link to the licence, and indicate if changes were made.

## Derived data — `data/processed/` and `index.html`

These are adaptations of the source data and are released under the **same CC BY 4.0 licence**.

Changes made relative to the source, as required by the licence:

- text hygiene: non-breaking and zero-width spaces removed, whitespace collapsed, blanks set to NA
- degree symbols stripped from coordinate fields
- free text in numeric fields moved to parallel `<field>_note` columns
- `+` lower-bound markers split into boolean `<field>_is_minimum` columns
- derived columns added: `year_best`, `year_precision`, `event_date`, `<field>_terms`,
  `<field>_is_placeholder`
- re-encoded as UTF-8

No source value was deleted or overwritten. `data/processed/qc_report.json` contains the complete
transformation log with row counts.

## Interpretation

Quality findings, severity ratings and version-diff verdicts in this repository are the analysis of
this repository's author, not of ICIMOD. In particular the "date or name refined" classifications
are inferred from spatial and temporal proximity, not from any published changelog.

This repository is independent and is not affiliated with or endorsed by ICIMOD.
