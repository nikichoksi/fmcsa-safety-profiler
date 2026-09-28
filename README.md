# FMCSA Carrier Safety Risk Profiler

Scores active U.S. motor carriers on safety risk using public FMCSA Safety Measurement System (SMS) data, and presents the results in an interactive Streamlit dashboard.

The source data covers 2.2M carriers, 5.9M roadside inspections, 6.9M violations and 258K crashes from August 2024 to July 2026. After filtering, 287,990 active carriers with at least 3 inspections are scored.

## Dashboard

- KPI row: carriers, critical-risk count, and average OOS, severity and crash rates for the current filter
- Risk tier distribution and average OOS rate by fleet peer group
- Fleet size vs. OOS rate scatter plot, colored by risk tier
- Sortable carrier table with CSV download
- Filters for risk tier, peer group, state and fleet size

## Methodology

### Metrics

| Metric | Definition |
|---|---|
| OOS rate | Share of inspections with at least one out-of-service violation |
| Severity rate | Total violation severity weight per inspection |
| Crash rate | Crashes per 100 power units (capped at 50) |

Each table is aggregated per carrier before joining, so crash and violation counts don't multiply each other.

### Small-sample adjustment

A carrier with 3 inspections and 1 OOS inspection has a raw OOS rate of 33%, which says little about its true risk. For tiering, each rate is shrunk toward the population mean (empirical Bayes):

```
adjusted_rate = (events + k × population_mean) / (exposure + k)
```

with `k = 10` inspections for OOS and severity rates, and `k = 20` power units for crash rate. The dashboard displays raw rates; adjusted rates are used only for tiering and table ranking.

### Risk tiers

Each carrier earns points by where its adjusted rates fall relative to all scored carriers:

| Factor | +1 | +2 | +3 |
|---|---|---|---|
| OOS rate | ≥ 75th pct | ≥ 90th pct | ≥ 95th pct |
| Severity rate | ≥ 75th pct | ≥ 90th pct | ≥ 95th pct |
| Crash rate* | ≥ 75th pct | ≥ 90th pct | — |
| Any fatality | ✓ | | |

\*Only carriers with at least one crash can earn crash points, and crash percentiles are computed among those carriers. Most carriers have no crashes, and without this rule the small-sample adjustment would flag small zero-crash fleets.

| Tier | Points | Carriers | Share |
|---|---|---|---|
| Low | 0–1 | 221,385 | 76.9% |
| Medium | 2–3 | 41,811 | 14.5% |
| High | 4–5 | 17,097 | 5.9% |
| Critical | 6+ | 7,697 | 2.7% |

### Peer groups

Carriers are clustered into four fleet-size peer groups with k-means on log-scaled power units and driver counts. Clusters are labeled Small to Extra Large by average fleet size. Because driver counts are included, power-unit ranges overlap between groups.

## Project structure

```
src/
  etl.py            Load SMS CSVs into SQLite (database/fmcsa.db)
  scoring.py        Compute rates, peer groups and risk tiers → safety_scores table
  export_scores.py  Export safety_scores to data/safety_scores.parquet
  dashboard.py      Streamlit dashboard
  verify.py         Quick sanity checks on the loaded database
data/
  safety_scores.parquet   Scored carriers (the only data file in the repo)
```

## Running locally

The dashboard runs from the committed Parquet file, so the raw data is only needed to rebuild scores.

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
streamlit run src/dashboard.py
```

### Rebuilding the scores

1. Download the SMS input files (Motor Carrier Census, Inspection, Violation, Crash) from the [FMCSA SMS downloads page](https://ai.fmcsa.dot.gov/SMS/Tools/Downloads.aspx) into `data/`. They total about 3.7 GB and are not committed.
2. Run the pipeline:

```bash
python src/etl.py            # build database/fmcsa.db
python src/scoring.py        # write the safety_scores table
python src/export_scores.py  # refresh data/safety_scores.parquet
```

When `database/fmcsa.db` exists, the dashboard reads from it; otherwise it reads the Parquet file. Re-run `export_scores.py` after every scoring run so the deployed app stays in sync.

## Limitations

- Risk tiers are relative (percentile-based), not an official FMCSA rating. A carrier's tier can change when other carriers' data changes.
- Crash counts include all reportable crashes regardless of fault.
- Rates are not time-weighted; FMCSA's own SMS weights recent events more heavily.
