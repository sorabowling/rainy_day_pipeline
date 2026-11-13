import pandas as pd

from payouts.pipeline import (
    clean_observations,
    compute_payouts,
    create_daily_table,
    load_observations,
    load_promises,
)


def test_data_loads():
    assert not load_observations().empty
    assert not load_promises().empty


def test_cleaning_and_daily_totals():
    # one duplicate and one invalid reading should leave two valid measurements.
    raw = pd.DataFrame({
        "station_id": ["A", "A", "A", "A"],
        "ts": [
            "2026-06-01T00:00:00Z",
            "2026-06-01T00:00:00Z",
            "2026-06-01T01:00:00Z",
            "2026-06-01T02:00:00Z",
        ],
        "precip_mm": [2.0, 2.0, 3.0, -9999.0],
    })
    cleaned = clean_observations(raw)
    daily = create_daily_table(cleaned)

    assert len(cleaned) == 3
    assert cleaned["precip_mm"].isna().sum() == 1
    assert str(cleaned["ts"].dt.tz) == "UTC"
    assert daily["rainfall_mm"].tolist() == [5.0]
    assert daily["valid_hour_count"].tolist() == [2]


def test_payout_threshold_and_dates():
    # our made up station has 5 days of data, but only 3 are within the promise's trip dates
    # the two 5 mm days are the trip's endpoints. the 20mm dates are outside of it
    daily = pd.DataFrame({
        "station_id": ["A"] * 5,
        "date": pd.date_range("2026-06-01", periods=5).date,
        "rainfall_mm": [20.0, 5.0, 0.0, 5.0, 20.0],
        "valid_hour_count": [24] * 5,
    })
    promises = pd.DataFrame({
        "promise_id": ["P1", "P2"],
        "station_id": ["A", "A"],
        "start_date": pd.to_datetime(["2026-06-02", "2026-06-02"]),
        "end_date": pd.to_datetime(["2026-06-04", "2026-06-04"]),
        "rain_threshold_mm": [5.0, 6.0],
    })
    payouts = compute_payouts(daily, promises)

    assert payouts["rainy_days"].tolist() == [2, 0]
    assert payouts["pays_out"].tolist() == [True, False]
    assert payouts["further_investigation"].tolist() == [False, False]


def test_missing_data_flags():
    # June 2 is unknown. June 3 already has enough rain despite its missing hour
    daily = pd.DataFrame({
        "station_id": ["A", "A", "A"],
        "date": pd.date_range("2026-06-01", periods=3).date,
        "rainfall_mm": [5.0, 0.0, 5.0],
        "valid_hour_count": [24, 12, 23],
    })
    promises = pd.DataFrame({
        "promise_id": ["incomplete", "already_paid", "no_station", "missing_date"],
        "station_id": ["A", "A", "B", "A"],
        "start_date": pd.to_datetime([
            "2026-06-01", "2026-06-01", "2026-06-01", "2026-06-03"
        ]),
        "end_date": pd.to_datetime([
            "2026-06-02", "2026-06-03", "2026-06-02", "2026-06-04"
        ]),
        "rain_threshold_mm": [5.0] * 4,
    })
    payouts = compute_payouts(daily, promises)

    assert payouts["rainy_days"].tolist() == [1, 2, 0, 1]
    assert payouts["unknown_days"].tolist() == [1, 1, 2, 1]
    assert payouts["pays_out"].tolist() == [False, True, False, False]
    assert payouts["further_investigation"].tolist() == [True, False, True, True]
