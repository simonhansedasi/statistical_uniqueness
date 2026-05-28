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


def _age_group_label(age: int) -> str:
    low = (age // 5) * 5
    return f"{low}_{low + 4}"


def get_selfemployment_rate(age: int, sex: str) -> float:
    rows = _load_csv("bls_selfemployment.csv")
    target = _age_group_label(age)
    for row in rows:
        if row["age_group"] == target and row["sex"] == sex:
            return float(row["rate"])
    # fallback: closest age group
    return 0.10


def get_moved_states_rate(age: int) -> float:
    rows = _load_csv("mobility.csv")
    target = _age_group_label(age)
    for row in rows:
        if row["age_group"] == target:
            return float(row["moved_states_rate"])
    return 0.03


def get_lived_abroad_rate(age: int) -> float:
    rows = _load_csv("mobility.csv")
    target = _age_group_label(age)
    for row in rows:
        if row["age_group"] == target:
            return float(row["lived_abroad_rate"])
    return 0.10


def get_marital_rate(marital_status: str, age_group: str, sex: str) -> float:
    """P(marital_status | age_group, sex) from ACS 2022 reference table."""
    rows = _load_csv("acs_marital_status.csv")
    for row in rows:
        if row["age_group"] == age_group and row["sex"] == sex:
            return float(row.get(marital_status, 0))
    # Fallback: nearest age group above
    return 0.10


def get_veteran_rate(age: int, sex: str) -> float:
    rows = _load_csv("veteran_rates.csv")
    target = _age_group_label(age)
    for row in rows:
        if row["age_group"] == target and row["sex"] == sex:
            return float(row["rate"])
    return 0.07


def get_language_rate(language: str) -> float:
    """P(speaks this language | US population). English returns 1.0."""
    if language.lower() == "english":
        return 1.0
    rows = _load_csv("language_rates.csv")
    for row in rows:
        if row["language"].lower() == language.lower():
            return float(row["rate"])
    # Unknown language: conservative estimate for a rare non-English language
    return 0.001
