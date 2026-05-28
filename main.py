import argparse
import sys
import yaml
from pathlib import Path

from engine.probability import compute_attribute_probs, compute_joint
from data.census import get_cohort_size
from report import print_report


def load_profile(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description="Compute how statistically unique you are.")
    parser.add_argument("--profile", default="profile.yaml", help="Path to profile YAML")
    parser.add_argument("--verbose", action="store_true", help="Show data sources and notes")
    args = parser.parse_args()

    profile_path = Path(args.profile)
    if not profile_path.exists():
        print(f"Profile not found: {profile_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading profile from {profile_path}...")
    profile = load_profile(profile_path)

    age = profile["meta"]["age"]
    sex = profile["meta"]["sex"]
    ag_5yr = f"{(age // 5) * 5}_{(age // 5) * 5 + 4}"

    print("Fetching population statistics (first run may take ~10s, then cached)...")
    cohort_size = get_cohort_size(ag_5yr, sex)

    print("Computing attribute probabilities...")
    results = compute_attribute_probs(profile)

    joint = compute_joint(results, cohort_size)
    print_report(profile, results, joint, verbose=args.verbose)


if __name__ == "__main__":
    main()
