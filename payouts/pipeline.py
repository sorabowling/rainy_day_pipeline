"""Rainy Day Payouts pipeline.
Run from the project root:  python -m payouts.pipeline
"""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"


def load_observations(data_dir: Path = DATA_DIR) -> pd.DataFrame:
    # order files by date
    files = sorted((data_dir / "observations").glob("*.jsonl")) 

    # append with list comprehension removes need for append pandas method
    observations = pd.concat(
        [pd.read_json(f, lines=True, convert_dates=False) for f in files],
        ignore_index=True,
    ) 

    # print count of duplicates and impossible rainfaill values
    print(f"Loaded {len(files)} files with {len(observations)} rows.")
    print("Extra identical rows:", observations.duplicated().sum())
    print("Negative rainfall readings:", (observations["precip_mm"] < 0).sum())

    # calculate total number of full dates
    timestamps = pd.to_datetime(observations["ts"], utc=True)
    days = (timestamps.max().date() - timestamps.min().date()).days + 1

    # check for 24 hourly records per day. count each timestamp once.
    stations = pd.read_csv(data_dir / "stations.csv")["station_id"]
    recorded_hours = timestamps.groupby(observations["station_id"]).nunique()
    recorded_hours = recorded_hours.reindex(stations, fill_value=0)
    missing_hours = days * 24 - recorded_hours
    print("Missing hourly records per station (full UTC days covered by the data):")
    print(missing_hours.to_string())

    # possible other checks incl multiple different entries per station-hour

    return observations


def load_promises(data_dir: Path = DATA_DIR) -> pd.DataFrame:
    # read the CSV and turn the start and end dates into datetime type
    promises = pd.read_csv(
        data_dir / "promises.csv", parse_dates=["start_date", "end_date"]
    )
    print(f"Loaded {len(promises)} promises.")
    return promises


def clean_observations(observations: pd.DataFrame) -> pd.DataFrame:
    # drop duplicates to avoid double-counting, drop_duplicates() keeps first occurence by default
    observations = observations.drop_duplicates().copy()

    # convert timestamps to datetime and UTC
    observations["ts"] = pd.to_datetime(observations["ts"], utc=True)

    # drop rows with negative precipitation values
    observations["precip_mm"] = observations["precip_mm"].mask(
        observations["precip_mm"] < 0
    )

    observations["date"] = observations["ts"].dt.date

    return observations


def write_parquet(observations: pd.DataFrame, out_dir: Path) -> None:
    # create the output folder and parent folders
    out_dir.mkdir(parents=True, exist_ok=True)

    # Save the hourly rows in separate date folders, such as date=2026-06-01.
    observations.to_parquet(
        out_dir,
        engine="pyarrow",
        partition_cols=["date"],  # column name that determins partition
        index=False,
        # replace the date folders we write so rerunning does not add copies
        existing_data_behavior="delete_matching",
    )
    print(f"Saved {len(observations)} observations to {out_dir}.")


def create_daily_table(observations: pd.DataFrame) -> pd.DataFrame:
    # agg one row per station-day
    return observations.groupby(["station_id", "date"], as_index=False).agg(
        rainfall_mm=("precip_mm", "sum"),
        valid_hour_count=("precip_mm", "count"),
    )


def match_promise_days(daily: pd.DataFrame, promises: pd.DataFrame) -> pd.DataFrame:
    promise_days = promises.merge(daily, on="station_id", how="inner")
    # select only days within promise start and end dates, inclusive
    promise_days = promise_days.loc[
        promise_days["date"].between(
            promise_days["start_date"].dt.date, promise_days["end_date"].dt.date
        )
    ].copy()

    promise_days["is_rainy"] = promise_days["rainfall_mm"] >= promise_days["rain_threshold_mm"]
    promise_days["is_unknown"] = (
        (promise_days["valid_hour_count"] < 24) & ~promise_days["is_rainy"]
    )
    return promise_days


def compute_payouts(daily: pd.DataFrame, promises: pd.DataFrame) -> pd.DataFrame:
    promise_days = match_promise_days(daily, promises)
    # sum booleans for each promise
    counts = promise_days.groupby("promise_id", as_index=False).agg(
        rainy_days=("is_rainy", "sum"),
        unknown_days=("is_unknown", "sum"),
        recorded_days=("date", "count"),
    )
    
    payouts = promises.merge(counts, on="promise_id", how="left")
    count_columns = ["rainy_days", "unknown_days", "recorded_days"]
    payouts[count_columns] = payouts[count_columns].fillna(0).astype(int)

    # count completely absent days as unknown as well
    trip_days = (payouts["end_date"] - payouts["start_date"]).dt.days + 1
    payouts["unknown_days"] += trip_days - payouts["recorded_days"]

    # pay for two confirmed rainy days. flag cases where missing data could change this.
    payouts["pays_out"] = payouts["rainy_days"] >= 2
    payouts["further_investigation"] = (
        ~payouts["pays_out"] & (payouts["rainy_days"] + payouts["unknown_days"] >= 2)
    )
    return payouts.drop(columns="recorded_days")


def main() -> None:
    observations = clean_observations(load_observations())
    write_parquet(observations, OUTPUT_DIR / "observations")

    daily = create_daily_table(observations)
    payouts = compute_payouts(daily, load_promises())
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payouts.to_csv(OUTPUT_DIR / "payouts.csv", index=False)
    print(payouts)


if __name__ == "__main__":
    main()
