from __future__ import annotations
from tabulate import tabulate
from engine.probability import AttrResult


def _fmt_prob(p: float) -> str:
    if p >= 0.10:
        return f"{p * 100:.1f}%"
    elif p >= 0.001:
        return f"{p * 100:.2f}%"
    else:
        return f"1 in {int(round(1 / p)):,}"


def _rarity_stars(p: float) -> str:
    if p < 0.001:
        return "****"
    elif p < 0.01:
        return "***"
    elif p < 0.05:
        return "**"
    elif p < 0.15:
        return "*"
    return ""


def _fmt_expected(n: float) -> str:
    if n < 1:
        return f"<1  (effectively unique)"
    elif n < 10:
        return f"~{n:.1f}"
    elif n < 1000:
        return f"~{int(round(n))}"
    elif n < 1_000_000:
        return f"~{n/1000:.1f}k"
    else:
        return f"~{n/1_000_000:.2f}M"


def print_report(profile: dict, results: list[AttrResult], joint: dict, verbose: bool = False):
    age = profile["meta"]["age"]
    sex = profile["meta"]["sex"]
    name = profile["meta"]["name"]
    cohort_size = joint["cohort_size"]

    print()
    print("STATISTICAL UNIQUENESS REPORT")
    print("=" * 56)
    print(f"  Profile : {name}  |  {sex.title()}, age {age}")
    print(f"  Cohort  : US {sex}s age {(age // 5) * 5}-{(age // 5) * 5 + 4}  "
          f"({cohort_size:,} people)")
    print()

    # Attribute rarity table
    rows = []
    for r in sorted(results, key=lambda x: x.prob, reverse=True):
        stars = _rarity_stars(r.prob)
        note = f"  [{r.note}]" if verbose and r.note else ""
        rows.append([
            r.name,
            r.value,
            _fmt_prob(r.prob),
            stars,
            r.source if verbose else "",
        ])

    headers = ["Attribute", "Your value", "Rate in cohort", "Rarity", "Source"] if verbose \
        else ["Attribute", "Your value", "Rate in cohort", ""]
    print("ATTRIBUTE RARITY")
    print(tabulate(rows, headers=headers, tablefmt="simple"))
    print()
    print("  * <15%   ** <5%   *** <1%   **** <0.1%")
    print()

    # Cumulative uniqueness
    print("CUMULATIVE UNIQUENESS  (rarest attribute added first)")
    print("-" * 56)
    cum_rows = []
    for entry in joint["cumulative"]:
        exp = entry["expected"]
        cum_rows.append([
            f"+ {entry['name']}",
            entry["value"],
            _fmt_prob(entry["prob"]),
            _fmt_expected(exp),
        ])
    print(tabulate(cum_rows,
                   headers=["Adding attribute", "Value", "P(attr|cohort)", "Running expected matches"],
                   tablefmt="simple"))
    print()

    # Result
    exp = joint["expected_matches"]
    one_in_n = int(round(1 / joint["joint_prob"])) if joint["joint_prob"] > 0 else 0
    print("RESULT")
    print("-" * 56)
    print(f"  Joint probability    : 1 in {one_in_n:,}")
    print(f"  Expected US matches  : {_fmt_expected(exp)}")

    sorted_attrs = joint["sorted_attrs"]
    if sorted_attrs:
        rarest = sorted_attrs[0]
        commonest = sorted_attrs[-1]
        print(f"  Most uniquifying     : {rarest.name} ({rarest.value}, {_fmt_prob(rarest.prob)})")
        print(f"  Most common          : {commonest.name} ({commonest.value}, {_fmt_prob(commonest.prob)})")

    print()
    print("  Note: Independence assumed between uncorrelated attributes.")
    print("  This underestimates expected matches (makes you appear MORE unique).")
    print("  Life-path conditional rates are conditioned on the outcome occurring.")
    print()


def _mini_bar(n: float, cohort: int) -> str:
    frac = min(n / cohort, 1.0)
    filled = int(frac * 20)
    return "[" + "#" * filled + "." * (20 - filled) + "]"
