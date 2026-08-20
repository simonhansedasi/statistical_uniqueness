# StatisticalUniqueness

How statistically rare are you? Fetches US Census data, computes per-attribute probabilities across your demographic profile, and reports your joint rarity as a 1-in-N.

Live at [uniquefier.us](https://uniquefier.us)

## How it works

Fill out `profile.yaml` with your demographics, life path, and family details. The tool fetches matching Census microdata (ACS PUMS), computes the frequency of each attribute in your age/sex cohort, then multiplies them to a joint probability.

```bash
python main.py --profile profile.yaml
python main.py --profile profile.yaml --verbose   # show data sources
```

The web app at `uniquefier.us` wraps the same engine in a form-based UI.

## Profile structure

```yaml
meta:
  name: "Simon"
  age: 33
  sex: "male"

demographics:
  race_ethnicity: "white_non_hispanic"
  education_level: "masters"
  occupation_group: "life_physical_social_science"
  household_income: 75000
  state: "WA"
  languages: ["estonian"]

family:
  marital_status: "married"
  num_children: 1
  housing_tenure: "rent"

life_path:
  age_at_first_marriage: 29
  age_at_first_child: 31
  founded_business: true
  moved_states: true
  lived_abroad: true
  foreign_born: false
  attended_grad_school: true
```

## Stack

Python, Flask, NumPy, pandas, PyYAML, US Census API (ACS PUMS)
