from __future__ import annotations
import math
from dataclasses import dataclass
from data import census, nsfg, bls, pums_lookup
from data.census import get_nativity_rate


@dataclass
class AttrResult:
    name: str
    value: str
    prob: float
    source: str
    note: str = ""


def _age_group_5yr(age: int) -> str:
    low = (age // 5) * 5
    return f"{low}_{low + 4}"


def compute_attribute_probs(profile: dict, state: str | None = None) -> list[AttrResult]:
    age = profile["meta"]["age"]
    sex = profile["meta"]["sex"]
    ag_5yr = _age_group_5yr(age)

    demo = profile.get("demographics") or {}
    fam = profile.get("family") or {}
    lp = profile.get("life_path") or {}

    results = []

    def _add(r):
        if r is not None:
            results.append(r)

    # ── Demographics ──────────────────────────────────────────────────────────

    race = demo.get("race_ethnicity")
    if race is not None:
        _add(AttrResult(
            name="race/ethnicity", value=race.replace("_", " "),
            prob=census.get_race_rate(race, state=state), source="ACS B03002",
        ))

    edu = demo.get("education_level")
    if edu is not None:
        _edu_prob = None
        _edu_note = "25+ population"
        _edu_src  = "ACS B15002"
        if race is not None:
            _edu_prob = census.get_education_rate_by_race(edu, race, sex, state=state)
            if _edu_prob is not None:
                _edu_note = f"conditional on {race.replace('_', ' ')}"
                _edu_src  = "ACS C15002"
        if _edu_prob is None:
            _edu_prob = census.get_education_rate(edu, sex, state=state)
        _add(AttrResult(
            name="education level", value=edu.replace("_", " "),
            prob=_edu_prob, source=_edu_src, note=_edu_note,
        ))

    occ = demo.get("occupation_group")
    if occ is not None:
        _occ_prob, _occ_src, _occ_note = pums_lookup.get_occupation_prob(occ, ag_5yr, sex, edu, state=state)
        _add(AttrResult(
            name="occupation group", value=occ.replace("_", " "),
            prob=_occ_prob, source=_occ_src, note=_occ_note,
        ))

    income = demo.get("household_income")
    if income is not None:
        _inc_prob, _inc_src, _inc_note = pums_lookup.get_income_prob(int(income), ag_5yr, sex, edu, state=state)
        _add(AttrResult(
            name="household income", value=_income_label(int(income)),
            prob=_inc_prob, source=_inc_src, note=_inc_note,
        ))

    # ── Family ────────────────────────────────────────────────────────────────

    marital = fam.get("marital_status")
    if marital is not None:
        _add(AttrResult(
            name="marital status", value=marital.replace("_", " "),
            prob=bls.get_marital_rate(marital, ag_5yr, sex),
            source="ACS 2022 reference",
        ))

    tenure = fam.get("housing_tenure")
    if tenure is not None:
        _ten_prob, _ten_src, _ten_note = pums_lookup.get_tenure_prob(tenure, ag_5yr, sex, marital, state=state)
        _add(AttrResult(
            name="housing tenure", value=tenure,
            prob=_ten_prob, source=_ten_src, note=_ten_note,
        ))

    num_children = fam.get("num_children")
    if num_children is not None:
        _add(AttrResult(
            name="number of children", value=str(num_children),
            prob=_children_rate(int(num_children), age, sex),
            source="ACS B13002 / CDC NCHS", note="approximate",
        ))

    # ── Languages ─────────────────────────────────────────────────────────────

    languages = demo.get("languages")
    if languages:
        for lang in languages:
            if lang.lower() != "english":
                _add(AttrResult(
                    name=f"speaks {lang}", value="yes",
                    prob=bls.get_language_rate(lang),
                    source="ACS B16001 / community estimates",
                ))

    # ── Life path — conditional numeric ──────────────────────────────────────

    age_marriage = lp.get("age_at_first_marriage")
    if age_marriage is not None and marital not in ("never_married", None):
        _add(AttrResult(
            name="age at first marriage", value=f"~{age_marriage}",
            prob=nsfg.get_marriage_age_rate(int(age_marriage), sex),
            source="NSFG 2017-2019", note="conditional on having married",
        ))

    age_child = lp.get("age_at_first_child")
    if age_child is not None and num_children is not None and int(num_children) > 0:
        _add(AttrResult(
            name="age at first child", value=f"~{age_child}",
            prob=nsfg.get_first_birth_rate(int(age_child), sex),
            source="NSFG 2017-2019", note="conditional on having children",
        ))

    # ── Life path — boolean attrs ──────────────────────────────────────────────

    def _bool(key, get_rate_fn, name, source, note=""):
        val = lp.get(key)
        if val is None:
            return
        rate = get_rate_fn()
        if rate is None:  # suppressed — another attribute makes this redundant
            return
        prob = rate if val else (1.0 - rate)
        _add(AttrResult(name=name, value="yes" if val else "no",
                        prob=prob, source=source, note=note))

    _bool("veteran",
          lambda: bls.get_veteran_rate(age, sex),
          "veteran", "ACS B21001")

    _bool("founded_business",
          lambda: bls.get_selfemployment_rate(age, sex),
          "self-employed / business", "BLS CPS 2022")

    _bool("moved_states",
          lambda: bls.get_moved_states_rate(age),
          "moved between states", "ACS B07001",
          note="annual mover rate; cumulative rate higher")

    _bool("lived_abroad",
          lambda: bls.get_lived_abroad_rate(age),
          "lived abroad 1+ year", "expat survey estimates",
          note="rough lifetime estimate ~10%")

    _bool("foreign_born",
          lambda: get_nativity_rate(state=state),
          "foreign-born", "ACS B05002",
          note="~14% nationally; varies widely by state")

    _bool("attended_grad_school",
          lambda: _grad_school_rate(sex, edu),
          "attended grad school", "ACS B15002",
          note=_grad_school_note(edu))

    return results


def compute_joint(results: list[AttrResult], cohort_size: int) -> dict:
    valid = [r for r in results if r.prob > 0]
    log_prob = sum(math.log(r.prob) for r in valid)
    joint_prob = math.exp(log_prob)
    expected_matches = joint_prob * cohort_size

    sorted_by_rarity = sorted(valid, key=lambda r: r.prob)
    cumulative = []
    running_log = 0.0
    for r in sorted_by_rarity:
        running_log += math.log(r.prob)
        cumulative.append({
            "name": r.name,
            "value": r.value,
            "prob": r.prob,
            "expected": math.exp(running_log) * cohort_size,
        })

    return {
        "joint_prob": joint_prob,
        "expected_matches": expected_matches,
        "sorted_attrs": sorted(valid, key=lambda r: r.prob),
        "cumulative": cumulative,
        "cohort_size": cohort_size,
    }


def _income_label(income: int) -> str:
    brackets = [
        (0, 9999, "<$10k"), (10000, 14999, "$10-15k"), (15000, 19999, "$15-20k"),
        (20000, 24999, "$20-25k"), (25000, 29999, "$25-30k"), (30000, 34999, "$30-35k"),
        (35000, 39999, "$35-40k"), (40000, 44999, "$40-45k"), (45000, 49999, "$45-50k"),
        (50000, 59999, "$50-60k"), (60000, 74999, "$60-75k"), (75000, 99999, "$75-100k"),
        (100000, 124999, "$100-125k"), (125000, 149999, "$125-150k"),
        (150000, 199999, "$150-200k"), (200000, 999999, "$200k+"),
    ]
    for lo, hi, label in brackets:
        if lo <= income <= hi:
            return label
    return "$200k+"


def _children_rate(num_children: int, age: int, sex: str) -> float:
    if sex == "male":
        dist = {0: 0.37, 1: 0.17, 2: 0.27, 3: 0.12, 4: 0.05, 5: 0.02}
    else:
        dist = {0: 0.33, 1: 0.18, 2: 0.29, 3: 0.13, 4: 0.05, 5: 0.02}
    return dist.get(min(num_children, 5), 0.01)


_GRAD_CONDITIONAL = {
    "bachelors":    0.35,  # ~35% of bachelor's holders attend some grad school (ACS PUMS estimate)
    "some_college": 0.04,
    "hs_diploma":   0.01,
    "less_than_hs": 0.005,
}


def _grad_school_rate(sex: str, education_level) -> float | None:
    # Graduate degree already implies grad school attendance — suppress to avoid double-counting
    if education_level in ("masters", "professional", "doctorate"):
        return None
    if education_level in _GRAD_CONDITIONAL:
        return _GRAD_CONDITIONAL[education_level]
    # Education excluded — fall back to marginal rate
    return (census.get_education_rate("masters", sex)
            + census.get_education_rate("professional", sex)
            + census.get_education_rate("doctorate", sex))


def _grad_school_note(education_level) -> str:
    if education_level in ("masters", "professional", "doctorate"):
        return "suppressed — implied by education level"
    if education_level in _GRAD_CONDITIONAL:
        return f"conditional on {education_level.replace('_', ' ')} as highest degree"
    return "marginal rate (education level excluded)"
