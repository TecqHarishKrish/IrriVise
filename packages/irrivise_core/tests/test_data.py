"""Weather validation, season extraction, chronological splits, synthetic fixture and NASA POWER parsing."""
import json

import httpx
import pandas as pd
import pytest

from irrivise_core.data import nasa_power
from irrivise_core.data.synthetic import generate_synthetic_weather
from irrivise_core.data.weather import WeatherValidationError, chronological_split, extract_seasons, read_weather_csv, validate_frame
from irrivise_core.util.repro import sha256_file

HEADER = "date,rain_mm,eto_mm,tmin_c,tmax_c\n"


def test_empty_and_header_only_csv_rejected():
    for text in ("", HEADER):
        with pytest.raises(WeatherValidationError):
            read_weather_csv(text=text)


def test_malformed_and_duplicate_dates_rejected():
    with pytest.raises(WeatherValidationError, match="malformed"):
        read_weather_csv(text=HEADER + "2025/01/01,0,4,20,30\n")
    with pytest.raises(WeatherValidationError, match="duplicated"):
        read_weather_csv(text=HEADER + "2025-01-01,0,4,20,30\n2025-01-01,0,4,20,30\n")


def test_negative_rain_and_inverted_temperature_rejected():
    with pytest.raises(WeatherValidationError, match="bounds"):
        read_weather_csv(text=HEADER + "2025-01-01,-1,4,20,30\n")
    with pytest.raises(WeatherValidationError, match="tmin_c > tmax_c"):
        read_weather_csv(text=HEADER + "2025-01-01,0,4,31,30\n")


def test_nan_rows_quarantined_not_imputed():
    frame, report = read_weather_csv(text=HEADER + "2025-01-01,0,4,20,30\n2025-01-02,NaN,4,20,30\n2025-01-03,1,4,20,30\n")
    assert len(frame) == 2 and report.quarantined_dates == ["2025-01-02"]
    assert report.missingness_pct["rain_mm"] > 0


def test_missing_columns_rejected():
    with pytest.raises(WeatherValidationError, match="Missing required"):
        validate_frame(pd.DataFrame({"date": ["2025-01-01"], "rain_mm": [0]}))


def test_season_extraction_skips_gaps():
    days = pd.date_range("2020-01-01", "2021-12-31")
    frame = pd.DataFrame({"date": days, "rain_mm": 0.0, "eto_mm": 4.0, "tmin_c": 20.0, "tmax_c": 30.0})
    frame = frame[frame["date"] != pd.Timestamp("2021-07-01")]
    seasons, skipped = extract_seasons(frame, "06-15", 140)
    assert [s.season_id for s in seasons] == ["2020"] and "2021" in skipped[0]


def test_chronological_split_is_ordered_and_disjoint():
    ids = [str(y) for y in range(2000, 2020)]
    s = chronological_split(ids)
    assert len(s.train) == 12 and len(s.validation) == 4 and len(s.test) == 4
    assert max(s.train) < min(s.validation) and max(s.validation) < min(s.test)
    assert chronological_split(["2020"]).train == () and chronological_split(["2020"]).test == ("2020",)


def test_synthetic_fixture_is_deterministic_and_committed(tmp_path):
    from irrivise_core.data.weather import write_weather_csv

    path = tmp_path / "w.csv"
    write_weather_csv(generate_synthetic_weather(), path)
    manifest = json.loads((nasa_power.Path(__file__).resolve().parents[3] / "data/manifests/synthetic_weather_tn_v1.json").read_text())
    assert sha256_file(path) == manifest["checksum_sha256"]


def _payload(days, time_standard="LST", fill_day=None):
    keys = [d.strftime("%Y%m%d") for d in days]
    values = {"T2M_MAX": 32.0, "T2M_MIN": 22.0, "PRECTOTCORR": 1.5, "ALLSKY_SFC_SW_DWN": 20.0, "WS2M": 2.0, "RH2M": 70.0}
    params = {p: {k: (-999.0 if k == fill_day else v) for k in keys} for p, v in values.items()}
    return {"header": {"time_standard": time_standard, "fill_value": -999.0}, "geometry": {"coordinates": [78.7, 10.79, 88.0]},
            "parameters": {p: {"units": u} for p, u in nasa_power.EXPECTED_UNITS.items()}, "properties": {"parameter": params}}


def test_nasa_power_parse_and_fao56_eto():
    from datetime import date
    days = pd.date_range("2020-01-01", "2020-01-05")
    frame, meta = nasa_power.parse_power(_payload(days, fill_day="20200103"), date(2020, 1, 1), date(2020, 1, 5), 10.79, "LST")
    assert frame["eto_mm"].iloc[0] == pytest.approx(nasa_power.fao56_eto(date(2020, 1, 1), 10.79, 88.0, 22, 32, 20, 2, rh_mean_pct=70))
    assert 2.0 < frame["eto_mm"].iloc[0] < 7.0
    assert pd.isna(frame["rain_mm"].iloc[2]) and meta["fill_value_count"] == 6
    with pytest.raises(nasa_power.PowerError, match="time standard"):
        nasa_power.parse_power(_payload(days, "UTC"), date(2020, 1, 1), date(2020, 1, 5), 10.79, "LST")


def test_nasa_power_download_cache_and_retries(tmp_path):
    from datetime import date
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(503)
        return httpx.Response(200, json=_payload(pd.date_range("2020-01-01", "2020-01-05")))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    m = nasa_power.download_power(10.79, 78.7, date(2020, 1, 1), date(2020, 1, 5), "LST", tmp_path, client=client, sleep=lambda s: None)
    assert m["rows"] == 5 and not m["cache_hit"] and len(calls) == 2
    m2 = nasa_power.download_power(10.79, 78.7, date(2020, 1, 1), date(2020, 1, 5), "LST", tmp_path, client=client, sleep=lambda s: None)
    assert m2["cache_hit"] and len(calls) == 2 and m2["checksum_sha256"] == m["checksum_sha256"]


def test_nasa_power_offline_fails_clearly(tmp_path):
    from datetime import date

    def handler(request):
        raise httpx.ConnectError("offline")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(nasa_power.PowerError, match="synthetic sample"):
        nasa_power.download_power(10.79, 78.7, date(2020, 1, 1), date(2020, 1, 5), "LST", tmp_path, client=client, sleep=lambda s: None)
    with pytest.raises(ValueError):
        nasa_power.build_query(95, 0, date(2020, 1, 1), date(2020, 1, 5), "LST")
