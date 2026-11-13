# Rainy Day Payouts

A local pandas pipeline that cleans hourly rainfall observations and produces one payout decision per promise.

## Setup (if you use the Python skeleton)

```
python -m venv .venv && source .venv/bin/activate
pip install pandas pyarrow pytest
pytest
python -m payouts.pipeline
```

## Run

Inputs belong in `data/observations/*.jsonl`, `data/stations.csv`, and `data/promises.csv`.
From the project root, install the dependencies, run the pipeline, and run the tests:

```bash
python3 -m pip install pandas pyarrow pytest
python3 -m payouts.pipeline
python3 -m pytest -q
```

## Outputs

- `output/observations/`: cleaned hourly observations saved as Parquet, partitioned by UTC date.
- `output/payouts.csv`: one row per promise, including `rainy_days`, `unknown_days`, `pays_out`, and `further_investigation`.

## Rules and assumptions

- Days are UTC calendar days. Both promise dates are included. A day is rainy when its rainfall reaches or exceeds that promise's threshold; two or more confirmed rainy days qualify for a payout.
- Identical duplicate observations are removed. Negative rainfall is invalid and replaced with `NaN`.
- Each station is expected to report once per hour: 24 valid readings per day. Daily rainfall sums the available readings; missing rainfall is not estimated.
- An incomplete day still qualifies if its recorded rain already reaches the threshold. Otherwise, it is unknown. Entirely absent dates are also unknown, including dates beyond the available observations.
- `further_investigation=True` means missing data could change the payout. In these cases, `pays_out=False` means no confirmed payout yet, not a definitive rejection. All promises remain in the output, including stations with no observations.
- No conflicting readings for the same station and timestamp were found. Detecting and handling such conflicts is a possible future improvement.

## AI disclaimer
- Claude and copilot assisted with auto-complete of basic pandas, improving comments, linting, overall functionality checks, and generating data for tests.