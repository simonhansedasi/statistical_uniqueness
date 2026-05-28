from __future__ import annotations
import os
import json
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

API_KEY = os.getenv("CENSUS_API_KEY", "")
BASE = "https://api.census.gov/data/2022/acs/acs5"

STATE_FIPS = {
    "al":"01","ak":"02","az":"04","ar":"05","ca":"06","co":"08","ct":"09",
    "de":"10","dc":"11","fl":"12","ga":"13","hi":"15","id":"16","il":"17",
    "in":"18","ia":"19","ks":"20","ky":"21","la":"22","me":"23","md":"24",
    "ma":"25","mi":"26","mn":"27","ms":"28","mo":"29","mt":"30","ne":"31",
    "nv":"32","nh":"33","nj":"34","nm":"35","ny":"36","nc":"37","nd":"38",
    "oh":"39","ok":"40","or":"41","pa":"42","pr":"72","ri":"44","sc":"45",
    "sd":"46","tn":"47","tx":"48","ut":"49","vt":"50","va":"51","wa":"53",
    "wv":"54","wi":"55","wy":"56",
}

STATE_NAMES = {
    "al":"Alabama","ak":"Alaska","az":"Arizona","ar":"Arkansas","ca":"California",
    "co":"Colorado","ct":"Connecticut","de":"Delaware","dc":"D.C.","fl":"Florida",
    "ga":"Georgia","hi":"Hawaii","id":"Idaho","il":"Illinois","in":"Indiana",
    "ia":"Iowa","ks":"Kansas","ky":"Kentucky","la":"Louisiana","me":"Maine",
    "md":"Maryland","ma":"Massachusetts","mi":"Michigan","mn":"Minnesota",
    "ms":"Mississippi","mo":"Missouri","mt":"Montana","ne":"Nebraska","nv":"Nevada",
    "nh":"New Hampshire","nj":"New Jersey","nm":"New Mexico","ny":"New York",
    "nc":"North Carolina","nd":"North Dakota","oh":"Ohio","ok":"Oklahoma",
    "or":"Oregon","pa":"Pennsylvania","pr":"Puerto Rico","ri":"Rhode Island",
    "sc":"South Carolina","sd":"South Dakota","tn":"Tennessee","tx":"Texas",
    "ut":"Utah","vt":"Vermont","va":"Virginia","wa":"Washington","wv":"West Virginia",
    "wi":"Wisconsin","wy":"Wyoming",
}


def _fetch(variables: list[str], state: str | None = None) -> dict[str, int]:
    prefix = f"state_{state}_" if state else ""
    cache_key = prefix + "_".join(sorted(variables))
    cache_file = CACHE_DIR / f"{cache_key[:120]}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())

    result = {}
    for i in range(0, len(variables), 49):
        chunk = variables[i:i + 49]
        geo = f"state:{STATE_FIPS[state]}" if state else "us:1"
        url = f"{BASE}?get={','.join(chunk)}&for={geo}&key={API_KEY}"
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        rows = resp.json()
        headers, values = rows[0], rows[1]
        for h, v in zip(headers, values):
            if h in variables and v is not None:
                try:
                    result[h] = int(v)
                except (ValueError, TypeError):
                    pass

    cache_file.write_text(json.dumps(result))
    return result


def _safe_rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator > 0 else 0.0


# ── Education (B15002: Sex by Educational Attainment, 25+ population) ────────

_EDU_VARS = {
    "male": {
        "total": "B15002_002E",
        "less_than_hs": [f"B15002_{i:03d}E" for i in range(3, 11)],
        "hs_diploma":   ["B15002_011E"],
        "some_college": ["B15002_012E", "B15002_013E", "B15002_014E"],
        "bachelors":    ["B15002_015E"],
        "masters":      ["B15002_016E"],
        "professional": ["B15002_017E"],
        "doctorate":    ["B15002_018E"],
    },
    "female": {
        "total": "B15002_019E",
        "less_than_hs": [f"B15002_{i:03d}E" for i in range(20, 28)],
        "hs_diploma":   ["B15002_028E"],
        "some_college": ["B15002_029E", "B15002_030E", "B15002_031E"],
        "bachelors":    ["B15002_032E"],
        "masters":      ["B15002_033E"],
        "professional": ["B15002_034E"],
        "doctorate":    ["B15002_035E"],
    },
}


def get_education_rate(edu_level: str, sex: str, state: str | None = None) -> float:
    mapping = _EDU_VARS[sex]
    all_vars = [mapping["total"]] + [v for vs in mapping.values() if isinstance(vs, list) for v in vs]
    data = _fetch(all_vars, state=state)
    total = data.get(mapping["total"], 0)
    count = sum(data.get(v, 0) for v in mapping.get(edu_level, []))
    return _safe_rate(count, total)


# ── Marital status (B12002: Sex by Marital Status by Age) ─────────────────────
# Age groups per sex: 15-17, 18-19, 20-24, 25-29, 30-34, 35-39, 40-44, 45-49, 50-54, 55-59, 60-64, 65-74, 75+
# Each group: total + 5 statuses = 6 variables per group

_MARITAL_STATUS_OFFSET = {
    "never_married": 1,
    "married":       2,   # "now married, except separated"
    "separated":     3,
    "widowed":       4,
    "divorced":      5,
}

_MARITAL_AGE_GROUPS = ["15_17", "18_19", "20_24", "25_29", "30_34", "35_39",
                       "40_44", "45_49", "50_54", "55_59", "60_64", "65_74", "75_plus"]


def _marital_var(sex: str, age_group: str, status_offset: int) -> str:
    sex_base = 2 if sex == "male" else 81
    group_idx = _MARITAL_AGE_GROUPS.index(age_group)
    group_start = sex_base + 1 + group_idx * 6  # +1 for the age total row
    return f"B12002_{(group_start + status_offset - 1):03d}E"


def _marital_total_var(sex: str, age_group: str) -> str:
    sex_base = 2 if sex == "male" else 81
    group_idx = _MARITAL_AGE_GROUPS.index(age_group)
    group_start = sex_base + 1 + group_idx * 6
    return f"B12002_{group_start:03d}E"


def get_marital_rate(marital_status: str, age_group: str, sex: str) -> float:
    offset = _MARITAL_STATUS_OFFSET.get(marital_status)
    if offset is None:
        return 0.0
    total_var = _marital_total_var(sex, age_group)
    status_var = _marital_var(sex, age_group, offset)
    data = _fetch([total_var, status_var])
    return _safe_rate(data.get(status_var, 0), data.get(total_var, 0))


# ── Household income (B19037: Age of Householder by Household Income) ─────────
# Age groups: 15_24, 25_44, 45_64, 65_plus
# B19037_019E = 25-44 total; buckets at _020E through _035E

_INCOME_BRACKETS = [
    (0,      9999,   "B19037_020E"),
    (10000,  14999,  "B19037_021E"),
    (15000,  19999,  "B19037_022E"),
    (20000,  24999,  "B19037_023E"),
    (25000,  29999,  "B19037_024E"),
    (30000,  34999,  "B19037_025E"),
    (35000,  39999,  "B19037_026E"),
    (40000,  44999,  "B19037_027E"),
    (45000,  49999,  "B19037_028E"),
    (50000,  59999,  "B19037_029E"),
    (60000,  74999,  "B19037_030E"),
    (75000,  99999,  "B19037_031E"),
    (100000, 124999, "B19037_032E"),
    (125000, 149999, "B19037_033E"),
    (150000, 199999, "B19037_034E"),
    (200000, 999999, "B19037_035E"),
]

_INCOME_TOTAL_VAR_25_44 = "B19037_019E"


def get_income_rate(income_usd: int, state: str | None = None) -> float:
    bracket_var = None
    for lo, hi, var in _INCOME_BRACKETS:
        if lo <= income_usd <= hi:
            bracket_var = var
            break
    if bracket_var is None:
        bracket_var = _INCOME_BRACKETS[-1][2]

    data = _fetch([_INCOME_TOTAL_VAR_25_44, bracket_var], state=state)
    return _safe_rate(data.get(bracket_var, 0), data.get(_INCOME_TOTAL_VAR_25_44, 0))


# ── Occupation (C24010: Sex by Occupation for Civilian Employed 16+) ──────────

_OCC_VARS_MALE = {
    "total":                        "C24010_002E",
    "management":                   "C24010_005E",
    "business_financial":           "C24010_006E",
    "computer_math":                "C24010_008E",
    "architecture_engineering":     "C24010_009E",
    "life_physical_social_science": "C24010_010E",
    "community_social_service":     "C24010_012E",
    "legal":                        "C24010_013E",
    "education_library":            "C24010_014E",
    "arts_design_entertainment":    "C24010_015E",
    "healthcare_practitioners":     "C24010_016E",
    "healthcare_support":           "C24010_019E",
    "protective_service":           "C24010_021E",
    "food_preparation":             "C24010_024E",
    "building_grounds":             "C24010_025E",
    "personal_care":                "C24010_026E",
    "sales":                        "C24010_028E",
    "office_admin":                 "C24010_029E",
    "farming_fishing":              "C24010_031E",
    "construction":                 "C24010_033E",
    "installation_maintenance":     "C24010_034E",
    "production":                   "C24010_036E",
    "transportation":               "C24010_037E",
}

_OCC_VARS_FEMALE = {
    "total":                        "C24010_039E",
    "management":                   "C24010_042E",
    "business_financial":           "C24010_043E",
    "computer_math":                "C24010_045E",
    "architecture_engineering":     "C24010_046E",
    "life_physical_social_science": "C24010_047E",
    "community_social_service":     "C24010_049E",
    "legal":                        "C24010_050E",
    "education_library":            "C24010_051E",
    "arts_design_entertainment":    "C24010_052E",
    "healthcare_practitioners":     "C24010_053E",
    "healthcare_support":           "C24010_056E",
    "protective_service":           "C24010_058E",
    "food_preparation":             "C24010_061E",
    "building_grounds":             "C24010_062E",
    "personal_care":                "C24010_063E",
    "sales":                        "C24010_065E",
    "office_admin":                 "C24010_066E",
    "farming_fishing":              "C24010_068E",
    "construction":                 "C24010_070E",
    "installation_maintenance":     "C24010_071E",
    "production":                   "C24010_073E",
    "transportation":               "C24010_074E",
}


def get_occupation_rate(occ_group: str, sex: str, state: str | None = None) -> float:
    mapping = _OCC_VARS_MALE if sex == "male" else _OCC_VARS_FEMALE
    var = mapping.get(occ_group)
    if var is None:
        return 0.0
    data = _fetch([mapping["total"], var], state=state)
    return _safe_rate(data.get(var, 0), data.get(mapping["total"], 0))


# ── Housing tenure (B25007: Tenure by Age of Householder) ─────────────────────
# Owner-occupied age groups: 15-24, 25-34, 35-44, 45-54, 55-59, 60-64, 65-74, 75-84, 85+
# Renter-occupied follows same structure

_TENURE_OWNER_VARS = {
    "15_24": "B25007_003E", "25_34": "B25007_004E", "35_44": "B25007_005E",
    "45_54": "B25007_006E", "55_59": "B25007_007E", "60_64": "B25007_008E",
    "65_74": "B25007_009E", "75_84": "B25007_010E", "85_plus": "B25007_011E",
}
_TENURE_RENTER_VARS = {
    "15_24": "B25007_013E", "25_34": "B25007_014E", "35_44": "B25007_015E",
    "45_54": "B25007_016E", "55_59": "B25007_017E", "60_64": "B25007_018E",
    "65_74": "B25007_019E", "75_84": "B25007_020E", "85_plus": "B25007_021E",
}

_TENURE_AGE_MAP = {
    "20_24": "15_24", "25_29": "25_34", "30_34": "25_34",
    "35_39": "35_44", "40_44": "35_44", "45_49": "45_54", "50_54": "45_54",
}


def get_tenure_rate(tenure: str, age_group: str, state: str | None = None) -> float:
    bucket = _TENURE_AGE_MAP.get(age_group, "35_44")
    owner_var = _TENURE_OWNER_VARS[bucket]
    renter_var = _TENURE_RENTER_VARS[bucket]
    data = _fetch([owner_var, renter_var], state=state)
    owner = data.get(owner_var, 0)
    renter = data.get(renter_var, 0)
    total = owner + renter
    if tenure == "own":
        return _safe_rate(owner, total)
    return _safe_rate(renter, total)


# ── Race / ethnicity (B03002: Hispanic or Latino Origin by Race) ───────────────

_RACE_VARS = {
    "total":               "B03002_001E",
    "white_non_hispanic":  "B03002_003E",
    "black_non_hispanic":  "B03002_004E",
    "aian":                "B03002_005E",
    "asian":               "B03002_006E",
    "nhopi":               "B03002_007E",
    "other":               "B03002_008E",
    "multiracial":         "B03002_009E",
    "hispanic":            "B03002_012E",
}


def get_race_rate(race_ethnicity: str, state: str | None = None) -> float:
    var = _RACE_VARS.get(race_ethnicity)
    if var is None:
        return 0.0
    data = _fetch([_RACE_VARS["total"], var], state=state)
    return _safe_rate(data.get(var, 0), data.get(_RACE_VARS["total"], 0))


# ── Cohort population size (B01001: Sex by Age) ────────────────────────────────

_COHORT_VARS_MALE = {
    "20_24": "B01001_010E", "25_29": "B01001_011E", "30_34": "B01001_012E",
    "35_39": "B01001_013E", "40_44": "B01001_014E", "45_49": "B01001_015E",
    "50_54": "B01001_016E",
}
_COHORT_VARS_FEMALE = {
    "20_24": "B01001_034E", "25_29": "B01001_035E", "30_34": "B01001_036E",
    "35_39": "B01001_037E", "40_44": "B01001_038E", "45_49": "B01001_039E",
    "50_54": "B01001_040E",
}


def get_cohort_size(age_group: str, sex: str, state: str | None = None) -> int:
    mapping = _COHORT_VARS_MALE if sex == "male" else _COHORT_VARS_FEMALE
    var = mapping.get(age_group)
    if var is None:
        return 1
    data = _fetch([var], state=state)
    return data.get(var, 1)


# ── Nativity (B05002: Place of Birth by Nativity and Citizenship) ─────────────

_NATIVITY_VARS = {
    "total":        "B05002_001E",
    "foreign_born": "B05002_013E",
}


def get_nativity_rate(state: str | None = None) -> float:
    """P(foreign-born) for the total population, optionally state-scoped."""
    data = _fetch([_NATIVITY_VARS["total"], _NATIVITY_VARS["foreign_born"]], state=state)
    return _safe_rate(data.get(_NATIVITY_VARS["foreign_born"], 0), data.get(_NATIVITY_VARS["total"], 0))


# ── Education conditional on race (C15002A-I: Sex by Edu by Race) ─────────────
# C15002X_002E = Male total,  _003=<HS, _004=HS, _005=some_col, _006=bach+
# C15002X_007E = Female total, _008=<HS, _009=HS, _010=some_col, _011=bach+

_RACE_LETTER = {
    "white_non_hispanic": "H",  # White alone, not Hispanic
    "black_non_hispanic": "B",  # Black alone
    "hispanic":           "I",  # Hispanic or Latino
    "asian":              "D",  # Asian alone
    "aian":               "C",  # American Indian and Alaska Native alone
    "nhopi":              "E",  # Native Hawaiian and Other Pacific Islander alone
    "multiracial":        "G",  # Two or more races
    "other":              "F",  # Some other race alone
}

# Within bach+, use B15002 to split into bach/masters/professional/doctorate
_BACH_PLUS_VARS_MALE   = ["B15002_015E", "B15002_016E", "B15002_017E", "B15002_018E"]
_BACH_PLUS_VARS_FEMALE = ["B15002_032E", "B15002_033E", "B15002_034E", "B15002_035E"]
_BACH_PLUS_LEVELS      = ["bachelors", "masters", "professional", "doctorate"]

_C15002_LOWER = {"less_than_hs", "hs_diploma", "some_college"}
_C15002_MALE_LOWER   = {"less_than_hs": 3, "hs_diploma": 4, "some_college": 5}
_C15002_FEMALE_LOWER = {"less_than_hs": 8, "hs_diploma": 9, "some_college": 10}


def get_education_rate_by_race(
    edu_level: str, race: str, sex: str, state: str | None = None
) -> float | None:
    """P(education | race, sex[, state]). Returns None if race not in mapping."""
    letter = _RACE_LETTER.get(race)
    if letter is None:
        return None

    X = f"C15002{letter}"
    if sex == "male":
        total_var = f"{X}_002E"
        bach_var  = f"{X}_006E"
        offset_map = _C15002_MALE_LOWER
    else:
        total_var = f"{X}_007E"
        bach_var  = f"{X}_011E"
        offset_map = _C15002_FEMALE_LOWER

    if edu_level in _C15002_LOWER:
        suffix = offset_map[edu_level]
        cat_var = f"{X}_{suffix:03d}E"
        data = _fetch([total_var, cat_var], state=state)
        total = data.get(total_var, 0)
        return _safe_rate(data.get(cat_var, 0), total) if total else None

    # bach+ levels: scale bach+ share by the within-bach+ split from B15002
    if edu_level not in _BACH_PLUS_LEVELS:
        return None

    bach_plus_vars = _BACH_PLUS_VARS_MALE if sex == "male" else _BACH_PLUS_VARS_FEMALE
    all_vars = [total_var, bach_var] + bach_plus_vars
    data = _fetch(all_vars, state=state)

    total     = data.get(total_var, 0)
    bach_plus = data.get(bach_var, 0)
    if total == 0 or bach_plus == 0:
        return None

    # P(bach+ | race, sex)
    p_bach_plus = _safe_rate(bach_plus, total)

    # P(edu_level | bach+, sex) from B15002 national
    split_total = sum(data.get(v, 0) for v in bach_plus_vars)
    idx = _BACH_PLUS_LEVELS.index(edu_level)
    split_count = data.get(bach_plus_vars[idx], 0)
    p_within = _safe_rate(split_count, split_total)

    return p_bach_plus * p_within
