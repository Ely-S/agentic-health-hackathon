# Codebook & Summary Statistics

Aggregate description of the dataset — the database schema, the 95 extracted variables,
and summary statistics. **No per-patient rows or free text are included here** (those stay
in the controlled dataset; see [PRIVACY.md](PRIVACY.md)).

The full machine-readable field dictionary is in
[`field_dictionary.csv`](field_dictionary.csv).

---

## Database schema (`patientpunk.db`)

| table | grain | rows |
|---|---|---|
| `unified` | one row per patient (wide) | 4,366 |
| `variables` | patient × field (long / EAV) | 39,707 |
| `treatment_reports` | patient × drug mention (sentiment) | 9,831 |
| `treatment` | canonical drug | 3,980 |
| `conditions` | patient × condition | 5,202 |
| `user_profiles` | patient (demographics) | 4,366 |
| `posts` | post/comment | 34,948 |
| `users` | patient (hashed id) | 4,368 |

Join key across tables: **`author_hash`**.

---

## The 95 extracted variables

Each patient has up to ~95 fields (avg **10.7** populated). Full per-field coverage,
example-value cardinality, and tags are in [`field_dictionary.csv`](field_dictionary.csv).
The columns there are:

`field, n_patients, coverage_pct_of_4366, distinct_values, top_5_values, category, medically_relevant, analysis_grade, note`

### Fields by category

| category | count | what it captures |
|---|---|---|
| phenotype | 34 | conditions, symptoms, severity, trajectory |
| treatment | 23 | medications, supplements, interventions, devices |
| experience | 11 | healthcare access, disability, psychosocial impact |
| demographic | 7 | age, sex, ethnicity, location, onset age |
| outcome | 5 | treatment response / sensitivity |
| biomarker | 5 | labs, autoantibodies, neuromarkers |
| noise | 5 | extraction artifacts — **excluded from analysis** |
| fringe | 5 | patient theories / speculation — use with caution |

By relevance tag: **74 "yes"** (clinical/biomedical) · **11 "adjacent"** (health-system /
psychosocial) · **10 "no"** (noise + fringe).

### Densest, analysis-grade fields (≥25% patient coverage)

These 8–11 fields anchor most analysis:

| field | coverage | example values |
|---|---|---|
| `conditions` | 58% | long covid, pem, mcas, pots, me/cfs |
| `prior_infections` | 49% | covid, ebv, lyme |
| `treatment_outcome` | 45% | helped, worsened, no_effect |
| `medications` | 38% | ldn, magnesium, paxlovid, ivig, b12 |
| `symptom_trajectory` | 31% | improving, relapsing, worsening, recovered |
| `medication_trial_outcome_category` | 29% | helped, flare up, no effect |
| `onset_trigger` | 26% | covid, reinfection, infection |
| `mental_health` | 23% | anxiety, therapy, depression |

> **Data-quality flags:** a few fields are noisy extraction artifacts (e.g.
> `targeted_symptom_domain`, `clinical_trial_participation`) and are tagged
> `medically_relevant = no` — filter them out. See the `note` column in the CSV.

---

## Summary statistics

### Conditions (top, by # patients)

| condition | patients |
|---|---|
| long covid | 1,698 |
| post-exertional malaise (PEM) | 660 |
| POTS | 527 |
| MCAS | 464 |
| ME/CFS | 390 |
| dysautonomia | 301 |
| post-viral | 162 |
| Ehlers-Danlos (EDS) | 81 |
| small fiber neuropathy | 77 |
| fibromyalgia | 56 |

These conditions heavily **co-occur** (the Long-COVID/dysautonomia overlap), which is part
of what the clustering/comorbidity views in the app explore.

### Treatments — the recommendation signal (top drugs by report volume)

9,831 reports; overall sentiment **76% positive / 21% negative / 3% mixed** (expect a
"what-helped-me" reporting bias). *Net* = (positive − negative) % of that drug's reports.

| drug | reports | net |
|---|---|---|
| low-dose naltrexone (LDN) | 447 | +63% |
| antihistamine | 247 | +49% |
| tirzepatide | 126 | +43% |
| magnesium | 105 | +82% |
| beta blocker | 97 | +68% |
| nattokinase | 93 | +66% |
| CoQ10 | 87 | +72% |
| vitamin D / B12 | 80 / 71 | +71% / +72% |
| SSRIs | 66 | +27% (most contested) |

(366 drugs have ≥5 reports — the analyzable set.)

### Demographics (sparse — self-reported)

Most users do not state demographics. Where present: age skews 20s–40s; of users stating
sex, ~55% female; locations are predominantly UK / US / Canada / NL / Germany. Coverage:
age ~6%, sex ~8%, location ~13%.

---

*All figures above are aggregate. The per-patient data they summarize is available under
controlled access only — see [DATASET.md](DATASET.md#getting-the-data).*
