"""
One-time data prep: download ACS 5-year 2022 PUMS person + housing files,
compute conditional probability tables, save as CSVs.

Per-state strategy: load housing file into dict (small, <100MB), then
stream-process person file in 50k-row chunks, joining on SERIALNO.

Outputs → data/reference/pums/:
  income_cond.csv      P(income_bracket | education, age_group, sex)
  occupation_cond.csv  P(occupation_group | education, age_group, sex)
  tenure_cond.csv      P(tenure | marital_status, age_group, sex)

Requirements: pip install pandas   (runtime app does NOT need pandas)
Usage:        python -m data.pums.build_tables
"""
from __future__ import annotations
import csv
import sys
import tempfile
import zipfile
from collections import defaultdict
from pathlib import Path

try:
    import pandas as pd
    import requests
except ImportError:
    sys.exit("Missing deps — run: pip install pandas requests")

PUMS_BASE = "https://www2.census.gov/programs-surveys/acs/data/pums/2022/5-Year/"
STATE_ABBRS = [
    "ak", "al", "ar", "az", "ca", "co", "ct", "dc", "de", "fl",
    "ga", "hi", "ia", "id", "il", "in", "ks", "ky", "la", "ma",
    "md", "me", "mi", "mn", "mo", "ms", "mt", "nc", "nd", "ne",
    "nh", "nj", "nm", "nv", "ny", "oh", "ok", "or", "pa", "pr",
    "ri", "sc", "sd", "tn", "tx", "ut", "va", "vt", "wa", "wi",
    "wv", "wy",
]
OUT_DIR   = Path(__file__).parents[2] / "data" / "reference" / "pums"
MIN_WEIGHT = 500  # min sum(PWGTP) to emit a probability cell

PERSON_COLS  = ["SERIALNO", "PWGTP", "AGEP", "SEX", "SCHL", "OCCP", "MAR"]
HOUSING_COLS = ["SERIALNO", "HINCP", "ADJINC", "TEN"]

# ── Category mappings ─────────────────────────────────────────────────────────

def _schl_to_edu(v) -> str | None:
    try:
        v = int(float(v))
    except (TypeError, ValueError):
        return None
    if v <= 15: return "less_than_hs"
    if v <= 17: return "hs_diploma"
    if v <= 20: return "some_college"
    if v == 21: return "bachelors"
    if v == 22: return "masters"
    if v == 23: return "professional"
    if v == 24: return "doctorate"
    return None


_OCC_RANGES = [
    (10,   440,  "management"),
    (500,  960,  "business_financial"),
    (1005, 1240, "computer_math"),
    (1300, 1560, "architecture_engineering"),
    (1600, 1980, "life_physical_social_science"),
    (2000, 2060, "community_social_service"),
    (2100, 2180, "legal"),
    (2200, 2555, "education_library"),
    (2600, 2970, "arts_design_entertainment"),
    (3000, 3550, "healthcare_practitioners"),
    (3600, 3655, "healthcare_support"),
    (3700, 3960, "protective_service"),
    (4000, 4160, "food_preparation"),
    (4200, 4255, "building_grounds"),
    (4300, 4650, "personal_care"),
    (4700, 4965, "sales"),
    (5000, 5940, "office_admin"),
    (6005, 6130, "farming_fishing"),
    (6200, 6765, "construction"),
    (6800, 6940, "installation_maintenance"),
    (7000, 7640, "production"),
    (7700, 8990, "transportation"),
    (9800, 9840, "protective_service"),
]

def _occp_to_group(v) -> str | None:
    try:
        v = int(float(v))
    except (TypeError, ValueError):
        return None
    for lo, hi, grp in _OCC_RANGES:
        if lo <= v <= hi:
            return grp
    return None


_INCOME_BRACKETS = [
    (0,         9_999,     "<$10k"),
    (10_000,   14_999,     "$10-15k"),
    (15_000,   19_999,     "$15-20k"),
    (20_000,   24_999,     "$20-25k"),
    (25_000,   29_999,     "$25-30k"),
    (30_000,   34_999,     "$30-35k"),
    (35_000,   39_999,     "$35-40k"),
    (40_000,   44_999,     "$40-45k"),
    (45_000,   49_999,     "$45-50k"),
    (50_000,   59_999,     "$50-60k"),
    (60_000,   74_999,     "$60-75k"),
    (75_000,   99_999,     "$75-100k"),
    (100_000, 124_999,     "$100-125k"),
    (125_000, 149_999,     "$125-150k"),
    (150_000, 199_999,     "$150-200k"),
    (200_000, 10_000_000,  "$200k+"),
]

def _income_to_bracket(adj_income: float) -> str | None:
    if adj_income < 0:
        return None
    for lo, hi, label in _INCOME_BRACKETS:
        if lo <= adj_income <= hi:
            return label
    return "$200k+"


_MAR_MAP = {1: "married", 2: "widowed", 3: "divorced", 4: "separated", 5: "never_married"}

def _sex_str(v) -> str | None:
    try:
        return "male" if int(float(v)) == 1 else "female"
    except (TypeError, ValueError):
        return None

def _age_group(v) -> str | None:
    try:
        age = int(float(v))
    except (TypeError, ValueError):
        return None
    if age < 18 or age > 90:
        return None
    low = (age // 5) * 5
    return f"{low}_{low + 4}"

# ── Accumulators ──────────────────────────────────────────────────────────────

income_counts:  defaultdict = defaultdict(float)
income_totals:  defaultdict = defaultdict(float)
occ_counts:     defaultdict = defaultdict(float)
occ_totals:     defaultdict = defaultdict(float)
tenure_counts:  defaultdict = defaultdict(float)
tenure_totals:  defaultdict = defaultdict(float)

# ── Download helper ───────────────────────────────────────────────────────────

def _download(url: str, label: str) -> Path:
    tmp = Path(tempfile.mktemp(suffix=".zip"))
    with requests.get(url, stream=True, timeout=(60, None)) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done  = 0
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
                done += len(chunk)
                if total:
                    print(f"  {label} {done/total*100:.0f}% ({done//1_000_000}MB/{total//1_000_000}MB)", end="\r")
    print(f"  {label} downloaded ({done//1_000_000} MB)        ")
    return tmp

# ── Per-state processing ───────────────────────────────────────────────────────

def _load_housing(zip_path: Path) -> dict:
    """Load SERIALNO → (income_bracket, tenure_str) from housing file."""
    housing: dict = {}
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            if not name.lower().endswith(".csv"):
                continue
            with zf.open(name) as f:
                avail = pd.read_csv(f, nrows=0).columns.tolist()
            needed = [c for c in HOUSING_COLS if c in avail]
            with zf.open(name) as f:
                for chunk in pd.read_csv(f, chunksize=100_000, usecols=needed, dtype=str, low_memory=False):
                    chunk = chunk.copy()
                    has_inc = "HINCP" in chunk.columns and "ADJINC" in chunk.columns
                    has_ten = "TEN" in chunk.columns

                    if has_inc:
                        h = pd.to_numeric(chunk["HINCP"],  errors="coerce")
                        a = pd.to_numeric(chunk["ADJINC"], errors="coerce")
                        adj = h * (a / 1_000_000)
                        chunk["_inc"] = adj.apply(
                            lambda x: _income_to_bracket(x) if pd.notna(x) else None
                        )
                    else:
                        chunk["_inc"] = None

                    if has_ten:
                        chunk["_ten"] = pd.to_numeric(chunk["TEN"], errors="coerce").apply(
                            lambda v: "own" if v in (1, 2) else ("rent" if v in (3, 4) else None)
                        )
                    else:
                        chunk["_ten"] = None

                    for sn, inc, ten in zip(chunk["SERIALNO"], chunk["_inc"], chunk["_ten"]):
                        if pd.notna(sn):
                            housing[str(sn)] = (inc, ten)
    return housing


def _process_person_chunk(chunk: pd.DataFrame, housing: dict) -> None:
    chunk = chunk.copy()
    chunk["_w"]   = pd.to_numeric(chunk["PWGTP"],  errors="coerce").fillna(0)
    chunk["_sex"] = chunk["SEX"].apply(_sex_str)
    chunk["_ag"]  = chunk["AGEP"].apply(_age_group)
    chunk["_edu"] = chunk["SCHL"].apply(_schl_to_edu)
    chunk["_occ"] = chunk["OCCP"].apply(_occp_to_group)
    chunk["_mar"] = chunk["MAR"].apply(
        lambda v: _MAR_MAP.get(int(float(v))) if pd.notna(v) else None
    )

    # Join housing data via SERIALNO
    sn_list = chunk["SERIALNO"].astype(str).tolist()
    h_data  = [housing.get(sn, (None, None)) for sn in sn_list]
    chunk["_inc"] = [h[0] for h in h_data]
    chunk["_ten"] = [h[1] for h in h_data]

    base = chunk["_sex"].notna() & chunk["_ag"].notna() & (chunk["_w"] > 0)

    # Income conditional
    m = base & chunk["_edu"].notna() & chunk["_inc"].notna()
    sub = chunk[m]
    if not sub.empty:
        g = sub.groupby(["_sex", "_ag", "_edu", "_inc"])["_w"].sum()
        for (sx, ag, edu, inc), wt in g.items():
            income_counts[(sx, ag, edu, inc)] += wt
        for (sx, ag, edu), wt in sub.groupby(["_sex", "_ag", "_edu"])["_w"].sum().items():
            income_totals[(sx, ag, edu)] += wt

    # Occupation conditional (employed only — OCCP not None)
    m = base & chunk["_edu"].notna() & chunk["_occ"].notna()
    sub = chunk[m]
    if not sub.empty:
        g = sub.groupby(["_sex", "_ag", "_edu", "_occ"])["_w"].sum()
        for (sx, ag, edu, occ), wt in g.items():
            occ_counts[(sx, ag, edu, occ)] += wt
        for (sx, ag, edu), wt in sub.groupby(["_sex", "_ag", "_edu"])["_w"].sum().items():
            occ_totals[(sx, ag, edu)] += wt

    # Tenure conditional
    m = base & chunk["_mar"].notna() & chunk["_ten"].notna()
    sub = chunk[m]
    if not sub.empty:
        g = sub.groupby(["_sex", "_ag", "_mar", "_ten"])["_w"].sum()
        for (sx, ag, mar, ten), wt in g.items():
            tenure_counts[(sx, ag, mar, ten)] += wt
        for (sx, ag, mar), wt in sub.groupby(["_sex", "_ag", "_mar"])["_w"].sum().items():
            tenure_totals[(sx, ag, mar)] += wt


def _process_state(abbr: str, idx: int, total: int) -> None:
    prefix = f"[{idx+1}/{total}] {abbr.upper()}"
    print(f"\n{prefix}")

    h_url = PUMS_BASE + f"csv_h{abbr}.zip"
    p_url = PUMS_BASE + f"csv_p{abbr}.zip"

    h_tmp = _download(h_url, f"{prefix} housing")
    try:
        housing = _load_housing(h_tmp)
    finally:
        h_tmp.unlink()

    p_tmp = _download(p_url, f"{prefix} persons")
    try:
        with zipfile.ZipFile(p_tmp) as zf:
            for name in zf.namelist():
                if not name.lower().endswith(".csv"):
                    continue
                with zf.open(name) as f:
                    avail = pd.read_csv(f, nrows=0).columns.tolist()
                    usecols = [c for c in PERSON_COLS if c in avail]
                with zf.open(name) as f:
                    for i, chunk in enumerate(
                        pd.read_csv(f, chunksize=50_000, usecols=usecols, dtype=str, low_memory=False)
                    ):
                        _process_person_chunk(chunk, housing)
                        print(f"  persons chunk {i+1:4d}", end="\r")
        print()
    finally:
        p_tmp.unlink()

# ── Write CSVs ────────────────────────────────────────────────────────────────

def _write_csvs() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    path = OUT_DIR / "income_cond.csv"
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["sex", "age_group", "education", "income_bracket", "prob", "n_weighted"])
        for (sx, ag, edu, bracket), wt in sorted(income_counts.items()):
            tot = income_totals.get((sx, ag, edu), 0)
            if tot < MIN_WEIGHT: continue
            w.writerow([sx, ag, edu, bracket, f"{wt/tot:.6f}", f"{tot:.0f}"])
    print(f"  income_cond.csv      {sum(1 for _ in open(path))-1:,} rows")

    path = OUT_DIR / "occupation_cond.csv"
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["sex", "age_group", "education", "occupation_group", "prob", "n_weighted"])
        for (sx, ag, edu, occ), wt in sorted(occ_counts.items()):
            tot = occ_totals.get((sx, ag, edu), 0)
            if tot < MIN_WEIGHT: continue
            w.writerow([sx, ag, edu, occ, f"{wt/tot:.6f}", f"{tot:.0f}"])
    print(f"  occupation_cond.csv  {sum(1 for _ in open(path))-1:,} rows")

    path = OUT_DIR / "tenure_cond.csv"
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["sex", "age_group", "marital_status", "tenure", "prob", "n_weighted"])
        for (sx, ag, mar, ten), wt in sorted(tenure_counts.items()):
            tot = tenure_totals.get((sx, ag, mar), 0)
            if tot < MIN_WEIGHT: continue
            w.writerow([sx, ag, mar, ten, f"{wt/tot:.6f}", f"{tot:.0f}"])
    print(f"  tenure_cond.csv      {sum(1 for _ in open(path))-1:,} rows")

# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    for i, abbr in enumerate(STATE_ABBRS):
        _process_state(abbr, i, len(STATE_ABBRS))

    print("\nWriting CSVs ...")
    _write_csvs()
    print(f"\nDone. Tables written to {OUT_DIR}")
