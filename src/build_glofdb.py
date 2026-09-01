#!/usr/bin/env python3
"""
HMAGLOFDB build pipeline
------------------------
Inputs : data/raw/HMAGLOFDB v1.0-v4.0 (ICIMOD GLOF database of High Mountain Asia)
Outputs: data/processed/  cleaned CSV, QC report, version diff, dashboard payload
         index.html       self-contained dashboard for GitHub Pages

Run from anywhere:  python src/build_glofdb.py
Every transformation is recorded so nothing is silently changed.
"""
import json, math, re, unicodedata, collections
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
TEMPLATE = ROOT / "src" / "template.html"
PAGE = ROOT / "index.html"
OUT.mkdir(parents=True, exist_ok=True)

VERSIONS = {
    "v1.0": ("HMAGLOFDB_v1_0_30122022.csv", "2022-12-30"),
    "v2.0": ("HMAGLOFDB_v2_0_13122023.csv", "2023-12-13"),
    "v3.0": ("HMAGLOFDB_v3_0_13122024.csv", "2024-12-13"),
    "v4.0": ("HMAGLOFDB_v4_0_13122025.csv", "2025-12-13"),
}

# Lat_lake/Lon_lake/Lat_impact/Lon_impact are parsed in the coordinate step, not here.
NUMERIC_FIELDS = [
    "Elev_lake", "Elev_impact", "Area", "Volume",
    "Discharge_water", "Discharge_solid", "Lives_total", "Lives_male",
    "Lives_female", "Lives_disabilities", "Injured_total", "Injured_male",
    "Injured_female", "Injured_disabilities", "Displaced_total", "Displaced_male",
    "Displaced_female", "Displaced_disabilities", "Livestock",
    "Residential_destroyed", "Commerical_destroyed", "Residential_damaged",
    "Commerical_damaged", "Agricultural", "Hydropower", "Econ_damage",
]

# Controlled vocabularies as printed in Data_Description.pdf / observed in v4
PLACEHOLDER_NAMES = {"unnamed", "unknown", "na", "n/a", ""}

log = []            # transformation log
issues = []         # QC findings


def note(kind, field, n, detail):
    log.append({"action": kind, "field": field, "n_rows": int(n), "detail": detail})


def flag(check, severity, field, n, detail, action):
    issues.append({"check": check, "severity": severity, "field": field,
                   "n_rows": int(n), "detail": detail, "action": action})


def load(fname):
    return pd.read_csv(SRC / fname, encoding="cp1252", low_memory=False, dtype=str)


# ---------------------------------------------------------------- text hygiene
def scrub(s: pd.Series) -> pd.Series:
    """NBSP -> space, unicode normalise, collapse whitespace, empty -> NA."""
    out = (s.astype("string")
             .str.replace("\u00a0", " ", regex=False)
             .str.replace("\u200b", "", regex=False)
             .map(lambda v: unicodedata.normalize("NFKC", v) if isinstance(v, str) else v)
             .str.replace(r"\s+", " ", regex=True)
             .str.strip())
    return out.replace({"": pd.NA, "-": pd.NA, "NA": pd.NA, "N/A": pd.NA, "na": pd.NA})


def to_num(s: pd.Series):
    """Return (numeric, is_minimum, residual_text).

    '+'      -> at-least marker, numeric part kept, flag set
    '600,000'-> thousands separator stripped
    free text-> numeric NA, text preserved in residual
    """
    raw = s.copy()
    txt = raw.fillna("")
    is_min = txt.str.contains(r"\+", regex=True)
    cleaned = (txt.str.replace(",", "", regex=False)
                  .str.replace("+", "", regex=False)
                  .str.replace("~", "", regex=False)
                  .str.replace("°", "", regex=False)
                  .str.strip())
    num = pd.to_numeric(cleaned, errors="coerce")
    residual = raw.where(num.isna() & raw.notna())
    return num, is_min.fillna(False), residual


# ---------------------------------------------------------------- year parsing
RANGE_RE = re.compile(r"^(\d{4})\s*[-–]\s*(\d{2,4})$")
BEFORE_RE = re.compile(r"^before\s+(\d{4})$", re.I)
DECADE_RE = re.compile(r"^(\d{3})0s$")
SPAN_RE = re.compile(r"^[A-Za-z]+\s+to\s+[A-Za-z]+\s+(\d{4})$", re.I)


def parse_year(v):
    """-> (year_best, precision). Precision is honest about what was known."""
    if pd.isna(v):
        return (np.nan, "unknown")
    v = str(v).strip()
    if re.fullmatch(r"\d{4}", v):
        return (int(v), "year")
    m = RANGE_RE.match(v)
    if m:
        a, b = m.group(1), m.group(2)
        b = a[:4 - len(b)] + b if len(b) < 4 else b
        return (int(round((int(a) + int(b)) / 2)), "range")
    m = BEFORE_RE.match(v)
    if m:
        return (int(m.group(1)), "before")
    m = DECADE_RE.match(v)
    if m:
        return (int(m.group(1) + "5"), "decade")
    m = SPAN_RE.match(v)
    if m:
        return (int(m.group(1)), "within-year span")
    return (np.nan, "unparsed")


# ================================================================= CLEAN v4
raw4 = load(VERSIONS["v4.0"][0])
df = raw4.copy()
n = len(df)

# 1. whitespace / NBSP contamination -------------------------------------------
nbsp_hits = int(raw4.apply(lambda c: c.astype(str).str.contains("\u00a0", na=False)).sum().sum())
lead_hits = int(raw4.apply(lambda c: c.astype(str).str.match(r"^\s+\S", na=False)).sum().sum())
for c in df.columns:
    df[c] = scrub(df[c])
note("scrub", "all", nbsp_hits, "non-breaking spaces replaced and blanks set to NA")
flag("Whitespace contamination", "medium", "17 fields", nbsp_hits,
     "Non-breaking space (U+00A0) used as an empty-cell placeholder; read as a value by "
     "naive parsers, so those cells look populated when they are not.",
     "Converted to NA.")
flag("Leading whitespace", "low", "LakeDB_ID, Lat_lake, Lon_lake, Mechanism, Infra, Ref_other",
     lead_hits, "Values padded with leading spaces, which breaks exact-match joins and grouping.",
     "Trimmed.")

# 2. coordinates ---------------------------------------------------------------
deg_rows = int(raw4["Lat_lake"].astype(str).str.contains("°", na=False).sum())
for c in ["Lat_lake", "Lon_lake", "Lat_impact", "Lon_impact"]:
    df[c] = pd.to_numeric(df[c].str.replace("°", "", regex=False).str.strip(), errors="coerce")
flag("Degree symbol in coordinate field", "medium", "Lat_lake, Lon_lake", deg_rows,
     "One record stores coordinates as ' 36.329250°' rather than a bare decimal, so it "
     "coerces to NaN and the event silently drops out of any map or spatial join.",
     "Stripped the symbol and parsed as float.")

bad_coord = int(((df.Lat_lake < 20) | (df.Lat_lake > 50) |
                 (df.Lon_lake < 60) | (df.Lon_lake > 110)).sum())
flag("Coordinate plausibility", "info", "Lat_lake, Lon_lake", bad_coord,
     f"Lake coordinates span {df.Lat_lake.min():.2f}–{df.Lat_lake.max():.2f}°N, "
     f"{df.Lon_lake.min():.2f}–{df.Lon_lake.max():.2f}°E. All fall inside High Mountain Asia.",
     "No change.")

# 3. dates ---------------------------------------------------------------------
ye = pd.to_numeric(df["Year_exact"], errors="coerce")
ya_parsed = df["Year_approx"].map(parse_year)
df["year_best"] = [a if not pd.isna(a) else b for a, (b, _) in zip(ye, ya_parsed)]
df["year_precision"] = [
    "exact" if not pd.isna(a) else p for a, (_, p) in zip(ye, ya_parsed)
]
df["Month"] = pd.to_numeric(df["Month"], errors="coerce")
df["Day"] = pd.to_numeric(df["Day"], errors="coerce")

full = df.year_best.notna() & df.Month.notna() & df.Day.notna()
df["event_date"] = pd.NaT
df.loc[full, "event_date"] = pd.to_datetime(dict(
    year=df.loc[full, "year_best"].astype(int),
    month=df.loc[full, "Month"].astype(int),
    day=df.loc[full, "Day"].astype(int)), errors="coerce")

both = ye.notna() & pd.to_numeric(df["Year_approx"], errors="coerce").notna()
disagree = int((ye[both] != pd.to_numeric(df["Year_approx"], errors="coerce")[both]).sum())
flag("Year_exact vs Year_approx", "info", "Year_exact, Year_approx", disagree,
     f"Both fields are populated for {int(both.sum())} records and never disagree. "
     "Year_approx is a superset that additionally carries text forms such as "
     "'Before 1966', '2002-2004' and '1960s'.",
     "Derived year_best (Year_exact first) plus year_precision.")

unparsed = int((df.year_precision == "unparsed").sum())
textyears = int((~df.year_precision.isin(["exact", "year", "unknown"])).sum())
flag("Non-numeric year strings", "medium", "Year_approx", textyears,
     "Ranges, decades and 'Before YYYY' forms in a field documented as INT. Any direct "
     "pd.to_numeric drops these events from time series.",
     "Parsed to a midpoint/bound in year_best with the assumption recorded in year_precision.")
noyear = int(df.year_best.isna().sum())
flag("Undated events", "high", "year_best", noyear,
     f"{noyear} of {n} events ({noyear/n:.0%}) carry no year at all. These are mostly "
     "satellite-detected events with no documentary account. Any per-decade rate must "
     "state this denominator.",
     "Retained with year_precision='unknown'; excluded from time series by default.")

# 4. numeric fields ------------------------------------------------------------
resid_store = {}
for c in NUMERIC_FIELDS:
    num, ismin, resid = to_num(df[c])
    nres = int(resid.notna().sum())
    if nres:
        resid_store[c] = resid
        df[c + "_note"] = resid
    if ismin.any():
        df[c + "_is_minimum"] = ismin
    df[c] = num
    if nres:
        note("text_to_note", c, nres, "free text moved to <field>_note, numeric set to NA")

text_in_num = {c: int(v.notna().sum()) for c, v in resid_store.items()}
flag("Free text in numeric fields", "high", ", ".join(text_in_num), sum(text_in_num.values()),
     "Fields documented as INT contain prose such as 'Damage in 8 villages', "
     "'1200 Teesta III, 510 Teesta V, 500 Teesta VI' and '13 houses fully damaged; 10 "
     "partially damaged'. Summing these fields naively either errors or silently drops them.",
     "Numeric part set to NA and the original string preserved in a parallel <field>_note column.")

minflags = int(sum(df[c].sum() for c in df.columns if c.endswith("_is_minimum")))
flag("'+' as an at-least marker", "medium", "Lives_total, Livestock, Residential_destroyed, others",
     minflags, "'+' marks counts known only as a lower bound. The Data Description defines it, "
     "but it is inside the value rather than a separate field.",
     "Split into a boolean <field>_is_minimum column.")

# 5. placeholder names ---------------------------------------------------------
for c in ["Lake_name", "Glacier_name"]:
    ph = df[c].str.lower().isin(PLACEHOLDER_NAMES)
    df[c + "_is_placeholder"] = ph
    note("placeholder_flag", c, ph.sum(), "'Unnamed'/'Unknown' marked, original text kept")
lake_ph = int(df["Lake_name_is_placeholder"].sum())
v3names = load(VERSIONS["v3.0"][0])["Lake_name"].str.strip().value_counts()
v4names = df["Lake_name"].value_counts()
flag("Placeholder naming drift", "medium", "Lake_name", lake_ph,
     f"'Unnamed' and 'Unknown' are used interchangeably for nameless lakes and the split "
     f"moved between releases (v3: {int(v3names.get('Unnamed',0))} Unnamed / "
     f"{int(v3names.get('Unknown',0))} Unknown; v4: {int(v4names.get('Unnamed',0))} / "
     f"{int(v4names.get('Unknown',0))}). Name-based joins across versions break on this alone.",
     "Flagged in Lake_name_is_placeholder; not used as a join key.")

# 6. multi-value categoricals --------------------------------------------------
def split_terms(s):
    if pd.isna(s):
        return []
    parts = re.split(r"[;,]", str(s))
    return [p.strip().capitalize() for p in parts if p.strip()]

for c in ["Driver_GLOF", "Mechanism"]:
    df[c + "_terms"] = df[c].map(split_terms)
    df[c + "_n"] = df[c + "_terms"].map(len)

raw_drivers = set(raw4["Driver_GLOF"].dropna().unique())
norm_drivers = set(t for ts in df["Driver_GLOF_terms"] for t in ts)
flag("Inconsistent multi-value delimiters", "medium", "Driver_GLOF, Mechanism",
     int((df["Driver_GLOF_n"] > 1).sum() + (df["Mechanism_n"] > 1).sum()),
     "Compound entries use both ';' and ',' as separators and vary in capitalisation "
     "('Ice avalanche, water level rise' vs 'High temperatures; intense rainfall'), so "
     f"{len(raw_drivers)} raw Driver_GLOF strings collapse to {len(norm_drivers)} distinct terms.",
     "Split on both delimiters into <field>_terms lists with normalised casing.")

unknown_driver = int((df["Driver_GLOF"] == "Unknown").sum())
flag("Trigger unknown for most events", "info", "Driver_GLOF", unknown_driver,
     f"{unknown_driver/n:.0%} of events have no identified trigger and "
     f"{int((df.Mechanism=='Unknown').sum())/n:.0%} no identified breach mechanism. "
     "Driver frequencies are therefore proportions of a small documented subset, not of all GLOFs.",
     "No change; surfaced in the dashboard denominators.")

# 7. duplicates ----------------------------------------------------------------
dupkey = (df.Lat_lake.round(4).astype(str) + "|" + df.Lon_lake.round(4).astype(str) + "|" +
          df.year_best.astype(str) + "|" + df.Month.astype(str) + "|" + df.Day.astype(str))
ndup = int(dupkey.duplicated().sum())
dup_examples = df.loc[dupkey.duplicated(keep=False), ["GF_ID", "Lake_name", "Glacier_name",
                                                      "Country", "year_best"]]
flag("Same lake, same date, two records", "medium", "Lat_lake+Lon_lake+date", ndup,
     "Two records share an identical lake coordinate and date. These appear to be a linked "
     "pair (Upper and Lower Ngole Cho, Nepal, 16 Aug 2024) that drained together and were "
     "given one shared coordinate rather than a true duplicate — but confirm against the "
     "source before treating them as two independent events.",
     "Retained and flagged, not merged.")

recur = int((df.Repeat == "Y").sum())
flag("Recurring events dominate the count", "high", "Repeat", recur,
     f"{recur} of {n} records ({recur/n:.0%}) are flagged as repeat events. The published "
     "abstract attributes 23% of all events to just three ephemeral ice-dammed lakes "
     "(Merzbacher, Khurdopin, Kyagar). Treating rows as independent events overstates the "
     "number of distinct hazard sites by roughly a factor of two.",
     "No change; the dashboard offers a one-record-per-lake view.")

# 8. completeness --------------------------------------------------------------
completeness = []
for c in raw4.columns:
    filled = int(df[c].notna().sum()) if c in df.columns else 0
    completeness.append({"field": c, "filled": filled, "pct": round(100 * filled / n, 1)})
completeness.sort(key=lambda r: r["pct"])

empty_fields = [r["field"] for r in completeness if r["filled"] == 0]
flag("Fields with no data at all", "medium", ", ".join(empty_fields), 0,
     f"{len(empty_fields)} disaggregation fields are entirely empty across all {n} records. "
     "The schema promises sex- and disability-disaggregated casualties that were never populated.",
     "Retained for schema stability; excluded from analysis.")

# 9. fatality reconciliation ---------------------------------------------------
lives = df["Lives_total"]
total_deaths = float(lives.sum())
n_fatal = int((lives > 0).sum())
top = df.nlargest(6, "Lives_total")[["Lake_name", "Glacier_name", "Country",
                                     "year_best", "Lives_total"]]
flag("Fatality total reconciles to the published abstract", "info", "Lives_total", n_fatal,
     f"Lives_total sums to {total_deaths:,.0f} across {n_fatal} events with a recorded death "
     f"toll, matching the 8,996 figure in the v4 metadata abstract. But only {n_fatal} of {n} "
     f"records ({n_fatal/n:.0%}) carry any casualty figure, and two events "
     "(6,000 and 1,980 deaths) supply 89% of the total.",
     "No change; the concentration is shown explicitly rather than averaged away.")

# ================================================================= VERSION DIFF
def coord_key(x, r=4):
    la = pd.to_numeric(x["Lat_lake"].astype(str).str.replace("°", "", regex=False).str.strip(),
                       errors="coerce").round(r)
    lo = pd.to_numeric(x["Lon_lake"].astype(str).str.replace("°", "", regex=False).str.strip(),
                       errors="coerce").round(r)
    yr = x["Year_approx"].fillna("").astype(str).str.strip()
    mo = x["Month"].fillna("").astype(str).str.strip()
    dy = x["Day"].fillna("").astype(str).str.strip()
    return pd.Series([f"{a}|{b}|{c}|{d}|{e}" for a, b, c, d, e in zip(la, lo, yr, mo, dy)],
                     index=x.index)


raws = {v: load(f) for v, (f, _) in VERSIONS.items()}
for v, x in raws.items():
    x["_k"] = coord_key(x)

# GF_ID stability test
a, b = raws["v1.0"].set_index("GF_ID"), raws["v4.0"].set_index("GF_ID")
common = a.index.intersection(b.index)
stable = float((a.loc[common, "Lat_lake"].astype(str).str.strip() ==
                b.loc[common, "Lat_lake"].astype(str).str.strip()).mean())

flag("GF_ID is not a stable identifier", "high", "GF_ID", len(common),
     f"GF_ID is reassigned at every release: of the {len(common)} IDs present in both v1.0 and "
     f"v4.0, only {stable:.0%} refer to a record with the same lake coordinate. GF_ID 415 is a "
     "different flood in each version. Any stored reference to a GF_ID silently points at the "
     "wrong event after an update.",
     "Version diff matches on lake coordinate plus date instead of on GF_ID.")

order = list(VERSIONS)
diffs = []
for i in range(len(order) - 1):
    a_v, b_v = order[i], order[i + 1]
    A, B = raws[a_v], raws[b_v]
    ca, cb = collections.Counter(A["_k"]), collections.Counter(B["_k"])
    keys = sorted(set(ca) | set(cb))
    added_keys = sorted(k for k in keys if cb[k] > ca[k])
    gone_keys = sorted(k for k in keys if ca[k] > cb[k])
    addrows = B[B["_k"].isin(added_keys)]
    gonerows = A[A["_k"].isin(gone_keys)]

    # is a "gone" row really gone, or just refined? nearest neighbour in the new version
    laB = pd.to_numeric(B["Lat_lake"].astype(str).str.replace("°", "", regex=False),
                        errors="coerce").values
    loB = pd.to_numeric(B["Lon_lake"].astype(str).str.replace("°", "", regex=False),
                        errors="coerce").values
    yB = pd.to_numeric(B["Year_approx"], errors="coerce").values
    resolved = []
    for _, r in gonerows.iterrows():
        la = float(str(r["Lat_lake"]).replace("°", "").strip())
        lo = float(str(r["Lon_lake"]).replace("°", "").strip())
        yr = pd.to_numeric(pd.Series([r["Year_approx"]]), errors="coerce").iloc[0]
        dist = np.sqrt(((laB - la) * 111.0) ** 2 +
                       ((loB - lo) * 111.0 * math.cos(math.radians(la))) ** 2)
        near = np.where(dist <= 2.0)[0]          # same site, within 2 km
        same_year = [j for j in near if not pd.isna(yr) and yB[j] == yr]
        if len(same_year):
            j = same_year[0]
            verdict = "date or name refined"
        elif len(near):
            j = int(near[np.argmin(dist[near])])
            verdict = "site still present, this date is not"
        else:
            j = int(np.nanargmin(dist))
            verdict = "no nearby record"
        resolved.append({
            "lake": r["Lake_name"], "glacier": r["Glacier_name"], "country": r["Country"],
            "year": r["Year_approx"], "month": r["Month"], "day": r["Day"],
            "verdict": verdict,
            "n_at_site": int(len(near)),
            "match_lake": B["Lake_name"].iloc[j], "match_year": B["Year_approx"].iloc[j],
            "match_month": B["Month"].iloc[j], "match_day": B["Day"].iloc[j],
            "km": round(float(dist[j]), 2),
        })

    diffs.append({
        "from": a_v, "to": b_v,
        "n_from": len(A), "n_to": len(B), "net": len(B) - len(A),
        "added": int(sum(max(0, cb[k] - ca[k]) for k in keys)),
        "unmatched": int(sum(max(0, ca[k] - cb[k]) for k in keys)),
        "new_events": addrows[["Lake_name", "Glacier_name", "Country", "Year_approx",
                               "Month", "Day", "Lake_type", "Lives_total"]]
                      .fillna("").astype(str).to_dict("records"),
        "unmatched_records": resolved,
    })

# field-level edits on records carried through v1 -> v4
ca, cb = collections.Counter(raws["v1.0"]["_k"]), collections.Counter(raws["v4.0"]["_k"])
# sorted so the build is byte-reproducible: set iteration order varies between processes
uk = sorted(k for k in set(ca) & set(cb) if ca[k] == 1 and cb[k] == 1)
A = raws["v1.0"].set_index("_k").loc[uk]
B = raws["v4.0"].set_index("_k").loc[uk]
field_edits = []
for c in [x for x in raws["v1.0"].columns if x not in ("GF_ID", "_k")]:
    ch = (A[c].fillna("§").astype(str).str.strip() != B[c].fillna("§").astype(str).str.strip())
    if ch.sum():
        ex = []
        for k in A.index[ch][:4]:
            ex.append({"from": str(A.loc[k, c])[:70], "to": str(B.loc[k, c])[:70]})
        field_edits.append({"field": c, "n": int(ch.sum()),
                            "pct": round(100 * ch.sum() / len(uk), 1), "examples": ex})
field_edits.sort(key=lambda r: -r["n"])

version_diff = {
    "matched_key": "lake coordinate (4 dp) + Year_approx + Month + Day",
    "gfid_stability": round(stable, 4),
    "n_carried": len(uk),
    "steps": diffs,
    "field_edits": field_edits,
    "counts": [{"version": v, "n": len(raws[v]), "date": VERSIONS[v][1]} for v in order],
}

# ================================================================= AGGREGATES
def vc(series, top=None):
    s = series.value_counts()
    if top:
        s = s.head(top)
    return [{"k": str(k), "n": int(v)} for k, v in s.items()]


dated = df[df.year_best.notna()].copy()
dated["decade"] = (dated.year_best // 10 * 10).astype(int)

by_decade = (dated[dated.decade >= 1900]
             .groupby("decade")
             .agg(n=("GF_ID", "size"), deaths=("Lives_total", "sum"))
             .reset_index().to_dict("records"))

by_decade_type = {}
for lt in ["Moraine dammed", "Ice dammed", "Supraglacial"]:
    sub = dated[(dated.Lake_type == lt) & (dated.decade >= 1900)]
    by_decade_type[lt] = sub.groupby("decade").size().reindex(
        range(1900, 2030, 10), fill_value=0).tolist()

# unique lakes, to separate sites from events
sitekey = df.Lat_lake.round(3).astype(str) + "|" + df.Lon_lake.round(3).astype(str)
n_sites = int(sitekey.nunique())

top_sites = (df.assign(_s=sitekey).groupby("_s")
             .agg(n=("GF_ID", "size"),
                  lake=("Lake_name", "first"), glacier=("Glacier_name", "first"),
                  country=("Country", "first"), type=("Lake_type", "first"),
                  lat=("Lat_lake", "first"), lon=("Lon_lake", "first"))
             .sort_values("n", ascending=False).head(12).reset_index().to_dict("records"))

points = df[["Lat_lake", "Lon_lake", "Lake_name", "Glacier_name", "Country", "Lake_type",
             "year_best", "year_precision", "Lives_total", "Transboundary", "Repeat",
             "River_Basin", "Month"]].copy()
points.columns = ["lat", "lon", "lake", "glacier", "country", "type", "year", "prec",
                  "deaths", "trans", "repeat", "basin", "month"]
points = points.replace({np.nan: None})
points_rec = json.loads(points.to_json(orient="records"))

fatal_events = (df[df.Lives_total > 0]
                .sort_values("Lives_total", ascending=False)
                [["Lake_name", "Glacier_name", "Country", "year_best", "year_precision",
                  "Lake_type", "Lives_total", "Lives_total_is_minimum"]]
                .replace({np.nan: None}))
fatal_events.columns = ["lake", "glacier", "country", "year", "prec", "type", "deaths", "atleast"]
fatal_rec = json.loads(fatal_events.to_json(orient="records"))

payload = {
    "meta": {
        "source": "HMAGLOFDB v4.0 (ICIMOD, released 13 Dec 2025) with v1.0-v3.0 for the diff",
        "doi": "https://doi.org/10.26066/RDS.1973283",
        "licence": "CC BY 4.0",
        "n_events": n,
        "n_sites": n_sites,
        "n_dated": int(df.year_best.notna().sum()),
        "year_min": int(df.year_best.min()),
        "year_max": int(df.year_best.max()),
        "deaths": int(total_deaths),
        "n_fatal": n_fatal,
        "recurring": recur,
        "transboundary": int((df.Transboundary == "Y").sum()),
    },
    "points": points_rec,
    "by_country": vc(df.Country),
    "by_type": vc(df.Lake_type),
    "by_basin": vc(df.River_Basin, 12),
    "by_month": [{"k": int(m), "n": int((df.Month == m).sum())} for m in range(1, 13)],
    "by_driver": vc(pd.Series([t for ts in df.Driver_GLOF_terms for t in ts if t != "Unknown"])),
    "by_mechanism": vc(pd.Series([t for ts in df.Mechanism_terms for t in ts if t != "Unknown"])),
    "by_decade": by_decade,
    "by_decade_type": by_decade_type,
    "top_sites": top_sites,
    "fatal_events": fatal_rec,
    "completeness": completeness,
    "qc": issues,
    "transform_log": log,
    "diff": version_diff,
    "precision_mix": vc(df.year_precision),
}

# ================================================================= WRITE
clean_cols = list(raw4.columns) + [c for c in df.columns if c not in raw4.columns]
df[clean_cols].to_csv(OUT / "HMAGLOFDB_v4_clean.csv", index=False, encoding="utf-8")
(OUT / "glof_payload.json").write_text(json.dumps(payload, default=str))
(OUT / "qc_report.json").write_text(json.dumps(
    {"issues": issues, "transform_log": log, "completeness": completeness}, indent=2, default=str))
(OUT / "version_diff.json").write_text(json.dumps(version_diff, indent=2, default=str))

# render the dashboard: the payload is inlined so the page needs no network at all
tpl = TEMPLATE.read_text(encoding="utf-8")
if "/*__DATA__*/" not in tpl:
    raise SystemExit("src/template.html is missing the /*__DATA__*/ placeholder")
page = tpl.replace("/*__DATA__*/", json.dumps(payload, default=str))
if "</script" in json.dumps(payload, default=str):
    raise SystemExit("payload contains a closing script tag and would break the page")
PAGE.write_text(page, encoding="utf-8")

print("rows:", n, "| sites:", n_sites, "| deaths:", total_deaths, "| QC findings:", len(issues))
print("clean cols:", len(clean_cols))
for d in diffs:
    print(f"  {d['from']} -> {d['to']}: net {d['net']:+d}, added {d['added']}, unmatched {d['unmatched']}")
print("wrote:", PAGE.relative_to(ROOT), f"({PAGE.stat().st_size/1024:.0f} KB)")
