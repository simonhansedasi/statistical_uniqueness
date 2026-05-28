from __future__ import annotations
import csv
from pathlib import Path

_REF = Path(__file__).parent / "reference"


def _load_csv(filename: str) -> list[dict]:
    rows = []
    with open(_REF / filename) as f:
        reader = csv.DictReader(row for row in f if not row.startswith("#"))
        for row in reader:
            rows.append(row)
    return rows


def _age_bin(age: int) -> str:
    if age < 20:
        return "under_20"
    elif age < 25:
        return "20_24"
    elif age < 30:
        return "25_29"
    elif age < 35:
        return "30_34"
    elif age < 40:
        return "35_39"
    else:
        return "40_plus"


def get_marriage_age_rate(age_at_marriage: int, sex: str) -> float:
    """P(married at age_bin | ever married, sex)"""
    rows = _load_csv("nsfg_marriage_age.csv")
    target = _age_bin(age_at_marriage)
    for row in rows:
        if row["age_bin"] == target and row["sex"] == sex:
            return float(row["prob"])
    return 0.05


def get_first_birth_rate(age_at_birth: int, sex: str) -> float:
    """P(first birth in age_bin | has children, sex)"""
    rows = _load_csv("nsfg_first_birth_age.csv")
    target = _age_bin(age_at_birth)
    for row in rows:
        if row["age_bin"] == target and row["sex"] == sex:
            return float(row["prob"])
    return 0.05
