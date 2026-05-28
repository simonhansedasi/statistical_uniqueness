from __future__ import annotations
import os
import sys
import math
import yaml
from pathlib import Path
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent))

from engine.probability import compute_attribute_probs, compute_joint
from data.census import get_cohort_size, STATE_NAMES

app = Flask(__name__)

DROPDOWN_OPTS = {
    "race_ethnicity": [
        ("white_non_hispanic", "White (non-Hispanic)"),
        ("hispanic", "Hispanic / Latino"),
        ("black_non_hispanic", "Black (non-Hispanic)"),
        ("asian", "Asian"),
        ("aian", "American Indian / Alaska Native"),
        ("nhopi", "Native Hawaiian / Pacific Islander"),
        ("multiracial", "Two or more races"),
        ("other", "Other"),
    ],
    "education_level": [
        ("less_than_hs", "Less than high school"),
        ("hs_diploma", "High school diploma / GED"),
        ("some_college", "Some college / associate's"),
        ("bachelors", "Bachelor's degree"),
        ("masters", "Master's degree"),
        ("professional", "Professional degree (JD, MD, etc.)"),
        ("doctorate", "Doctorate (PhD)"),
    ],
    "occupation_group": [
        ("management", "Management"),
        ("business_financial", "Business & Financial"),
        ("computer_math", "Computer & Math"),
        ("architecture_engineering", "Architecture & Engineering"),
        ("life_physical_social_science", "Life, Physical & Social Science"),
        ("community_social_service", "Community & Social Service"),
        ("legal", "Legal"),
        ("education_library", "Education & Library"),
        ("arts_design_entertainment", "Arts, Design & Entertainment"),
        ("healthcare_practitioners", "Healthcare Practitioners"),
        ("healthcare_support", "Healthcare Support"),
        ("protective_service", "Protective Service / Military"),
        ("food_preparation", "Food Preparation & Serving"),
        ("building_grounds", "Building & Grounds"),
        ("personal_care", "Personal Care & Service"),
        ("sales", "Sales"),
        ("office_admin", "Office & Admin Support"),
        ("farming_fishing", "Farming, Fishing & Forestry"),
        ("construction", "Construction & Extraction"),
        ("installation_maintenance", "Installation & Maintenance"),
        ("production", "Production / Manufacturing"),
        ("transportation", "Transportation & Moving"),
    ],
    "marital_status": [
        ("never_married", "Never married"),
        ("married", "Married"),
        ("divorced", "Divorced"),
        ("separated", "Separated"),
        ("widowed", "Widowed"),
    ],
    "housing_tenure": [
        ("rent", "Renting"),
        ("own", "Owns / buying home"),
    ],
}

BOOLEAN_ATTRS = [
    ("veteran",           "Veteran (military service)"),
    ("founded_business",  "Self-employed / runs a business"),
    ("moved_states",      "Lived in 2+ US states"),
    ("lived_abroad",      "Lived outside US 1+ year"),
    ("foreign_born",      "Foreign-born (immigrant)"),
    ("attended_grad_school", "Attended graduate school"),
]

KNOWN_LANGUAGES = sorted([
    "arabic", "chinese", "danish", "dutch", "estonian", "finnish",
    "french", "german", "greek", "gujarati", "haitian_creole", "hindi",
    "hmong", "italian", "japanese", "korean", "latvian", "lithuanian",
    "norwegian", "persian", "polish", "portuguese", "punjabi", "russian",
    "spanish", "swedish", "tagalog", "telugu", "urdu", "vietnamese",
])


def _load_default_profile() -> dict:
    try:
        with open(Path(__file__).parent / "profile.yaml") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _build_profile(data: dict) -> tuple[dict, int, str, str | None]:
    age = int(data.get("age") or 33)
    sex = str(data.get("sex") or "male")
    state = data.get("state") or None
    if state == "us":
        state = None

    def _get(key, cast=str):
        inc = data.get(f"{key}_include", True)
        val = data.get(key)
        if not inc or val is None or val == "":
            return None
        try:
            return cast(val)
        except (ValueError, TypeError):
            return None

    def _getbool(key):
        inc = data.get(f"{key}_include", True)
        val = data.get(key)
        if not inc or val is None:
            return None
        if isinstance(val, bool):
            return val
        return str(val).lower() in ("true", "1", "yes")

    langs = data.get("languages") or []
    langs_include = data.get("languages_include", True)
    languages = [l for l in langs if l] if langs_include else []

    profile = {
        "meta": {"name": data.get("name", "User"), "age": age, "sex": sex},
        "demographics": {
            "race_ethnicity":   _get("race_ethnicity"),
            "education_level":  _get("education_level"),
            "occupation_group": _get("occupation_group"),
            "household_income": _get("household_income", int),
            "languages":        languages if languages else None,
        },
        "family": {
            "marital_status":  _get("marital_status"),
            "num_children":    _get("num_children", int),
            "housing_tenure":  _get("housing_tenure"),
        },
        "life_path": {
            "age_at_first_marriage": _get("age_at_first_marriage", int),
            "age_at_first_child":    _get("age_at_first_child", int),
            "veteran":               _getbool("veteran"),
            "founded_business":      _getbool("founded_business"),
            "moved_states":          _getbool("moved_states"),
            "lived_abroad":          _getbool("lived_abroad"),
            "foreign_born":          _getbool("foreign_born"),
            "attended_grad_school":  _getbool("attended_grad_school"),
        },
    }
    ag_5yr = f"{(age // 5) * 5}_{(age // 5) * 5 + 4}"
    cohort_size = get_cohort_size(ag_5yr, sex, state=state)
    location = STATE_NAMES[state] if state else "US"
    cohort_label = f"{location} {sex}s age {(age // 5) * 5}–{(age // 5) * 5 + 4}"
    return profile, cohort_size, cohort_label, state


def _fmt_expected(n: float) -> str:
    if n < 1:
        return "<1"
    elif n < 10:
        return f"{n:.1f}"
    elif n < 1000:
        return str(int(round(n)))
    elif n < 1_000_000:
        return f"{n / 1000:.1f}k"
    else:
        return f"{n / 1_000_000:.2f}M"


@app.route("/")
def index():
    state_opts = sorted(STATE_NAMES.items(), key=lambda x: x[1])
    return render_template(
        "index.html",
        dropdown_opts=DROPDOWN_OPTS,
        boolean_attrs=BOOLEAN_ATTRS,
        known_languages=KNOWN_LANGUAGES,
        profile={},
        state_opts=state_opts,
    )


@app.route("/calculate", methods=["POST"])
def calculate():
    data = request.get_json(force=True) or {}
    try:
        profile, cohort_size, cohort_label, state = _build_profile(data)
        results = compute_attribute_probs(profile, state=state)
        joint = compute_joint(results, cohort_size)

        one_in_n = int(round(1 / joint["joint_prob"])) if joint["joint_prob"] > 1e-30 else 0
        exp_matches = joint["expected_matches"]

        return jsonify({
            "ok": True,
            "cohort_size": cohort_size,
            "cohort_label": cohort_label,
            "one_in_n": one_in_n,
            "expected_matches": exp_matches,
            "expected_matches_fmt": _fmt_expected(exp_matches),
            "attributes": [
                {
                    "name":   r.name,
                    "value":  r.value,
                    "prob":   r.prob,
                    "source": r.source,
                    "note":   r.note,
                }
                for r in joint["sorted_attrs"]
            ],
            "cumulative": [
                {
                    "name":     e["name"],
                    "value":    e["value"],
                    "prob":     e["prob"],
                    "expected": e["expected"],
                    "expected_fmt": _fmt_expected(e["expected"]),
                }
                for e in joint["cumulative"]
            ],
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5005))
    app.run(host="0.0.0.0", port=port, debug=False)
