import json
from datetime import date

import httpx
import pytest

from irrivise_core.nasa_power import PARAMETERS, EXPECTED_UNITS, download_power, fao56_eto, parse_power


def test_fao56_published_daily_example():
    # FAO Irrigation and Drainage Paper 56, Chapter 4, Example 18: 3.88 mm/day.
    calculated = fao56_eto(date(2025, 7, 6), 50.8, 100, 12.3, 21.5, 22.07, 2.078, rh_min_pct=63, rh_max_pct=84)
    assert calculated == pytest.approx(3.88, abs=0.03)


def test_power_fetch_validation_and_cache(tmp_path):
    payload = {"header": {"time_standard": "UTC", "fill_value": -999}, "geometry": {"coordinates": [78.7, 10.79, 163.36]}, "parameters": {name: {"units": unit} for name, unit in EXPECTED_UNITS.items()}, "properties": {"parameter": {name: {"20240101": value} for name, value in zip(PARAMETERS, (31.08, 18.66, 0, 17.01, 2.35, 77.86))}}}
    calls = []
    def respond(request):
        calls.append(str(request.url))
        assert request.url.host == "power.larc.nasa.gov"
        return httpx.Response(200, json=payload)
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        manifest = download_power(10.79, 78.7, date(2024, 1, 1), date(2024, 1, 1), "UTC", tmp_path, client)
        again = download_power(10.79, 78.7, date(2024, 1, 1), date(2024, 1, 1), "UTC", tmp_path, client)
    assert manifest == again
    assert manifest["days"] == 1
    assert len(calls) == 1
    assert (tmp_path / manifest["processed_path"]).exists()
    payload["properties"]["parameter"]["RH2M"]["20240101"] = -999
    with pytest.raises(ValueError, match="missing RH2M"):
        parse_power(payload, date(2024, 1, 1), date(2024, 1, 1), 10.79, "UTC")
