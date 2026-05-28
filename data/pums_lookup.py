"""
Runtime conditional probability lookups backed by PUMS-derived CSVs.
Falls back to marginal Census/BLS rates when a cell is missing or the
CSVs haven't been built yet.

No pandas dependency — uses csv module only.
"""
from __future__ import annotations
import csv
import sys
from pathlib import Path

from data import census

_PUMS_DIR = Path(__file__).parent / "reference" / "pums"

# ── Load tables at import time ─────────────────────────────────────────────────

def _load(filename: str):
    """Yield rows from a PUMS reference CSV, or yield nothing if file absent."""
    path = _PUMS_DIR / filename
    if not path.exists():
        return
    with open(path) as f:
        yield from csv.DictReader(f)


def _load_income() -> dict:
    # {(sex, age_group, education): {income_bracket: prob}}
    t: dict = {}
    for row in _load("income_cond.csv"):
        key = (row["sex"], row["age_group"], row["education"])
        t.setdefault(key, {})[row["income_bracket"]] = float(row["prob"])
    return t


def _load_occupation() -> dict:
    # {(sex, age_group, education): {occupation_group: prob}}
    t: dict = {}
    for row in _load("occupation_cond.csv"):
        key = (row["sex"], row["age_group"], row["education"])
        t.setdefault(key, {})[row["occupation_group"]] = float(row["prob"])
    return t


def _load_tenure() -> dict:
    # {(sex, age_group, marital_status): {tenure: prob}}
    t: dict = {}
    for row in _load("tenure_cond.csv"):
        key = (row["sex"], row["age_group"], row["marital_status"])
        t.setdefault(key, {})[row["tenure"]] = float(row["prob"])
    return t


def _warn_once(msg: str, _seen: set = set()) -> None:
    if msg not in _seen:
        print(f"[pums_lookup] {msg}", file=sys.stderr)
        _seen.add(msg)


_income_table: dict = _load_income()
_occ_table:    dict = _load_occupation()
_tenure_table: dict = _load_tenure()

if not _income_table:
    _warn_once("PUMS tables not found — run: python -m data.pums.build_tables. Falling back to marginal rates.")


# ── Income ────────────────────────────────────────────────────────────────────

def _income_bracket(income_usd: int) -> str:
    brackets = [
        (0, 9_999, "<$10k"), (10_000, 14_999, "$10-15k"), (15_000, 19_999, "$15-20k"),
        (20_000, 24_999, "$20-25k"), (25_000, 29_999, "$25-30k"), (30_000, 34_999, "$30-35k"),
        (35_000, 39_999, "$35-40k"), (40_000, 44_999, "$40-45k"), (45_000, 49_999, "$45-50k"),
        (50_000, 59_999, "$50-60k"), (60_000, 74_999, "$60-75k"), (75_000, 99_999, "$75-100k"),
        (100_000, 124_999, "$100-125k"), (125_000, 149_999, "$125-150k"),
        (150_000, 199_999, "$150-200k"), (200_000, 10_000_000, "$200k+"),
    ]
    for lo, hi, label in brackets:
        if lo <= income_usd <= hi:
            return label
    return "$200k+"


def get_income_prob(
    income_usd: int, age_group: str, sex: str, education: str | None = None,
    state: str | None = None,
) -> tuple[float, str, str]:
    """P(income_bracket | education, age_group, sex) or marginal fallback."""
    if education and _income_table:
        bracket = _income_bracket(income_usd)
        cell = _income_table.get((sex, age_group, education), {})
        if bracket in cell:
            return (
                cell[bracket],
                "ACS PUMS 5yr 2022",
                f"conditional on {education.replace('_', ' ')}",
            )
    # Fallback: marginal rate from Census API
    prob = census.get_income_rate(income_usd, state=state)
    return prob, "ACS B19037", "marginal rate (age 25-44)"


# ── Occupation ─────────────────────────────────────────────────────────────────

def get_occupation_prob(
    occ_group: str, age_group: str, sex: str, education: str | None = None,
    state: str | None = None,
) -> tuple[float, str, str]:
    """P(occupation_group | education, age_group, sex) or marginal fallback."""
    if education and _occ_table:
        cell = _occ_table.get((sex, age_group, education), {})
        if occ_group in cell:
            return (
                cell[occ_group],
                "ACS PUMS 5yr 2022",
                f"conditional on {education.replace('_', ' ')}",
            )
    prob = census.get_occupation_rate(occ_group, sex, state=state)
    return prob, "ACS C24010", "marginal rate"


# ── Tenure ─────────────────────────────────────────────────────────────────────

def get_tenure_prob(
    tenure: str, age_group: str, sex: str, marital_status: str | None = None,
    state: str | None = None,
) -> tuple[float, str, str]:
    """P(tenure | marital_status, age_group, sex) or marginal fallback."""
    if marital_status and _tenure_table:
        cell = _tenure_table.get((sex, age_group, marital_status), {})
        if tenure in cell:
            return (
                cell[tenure],
                "ACS PUMS 5yr 2022",
                f"conditional on {marital_status.replace('_', ' ')}",
            )
    prob = census.get_tenure_rate(tenure, age_group, state=state)
    return prob, "ACS B25007", "marginal rate"
