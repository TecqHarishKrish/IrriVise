from datetime import date, timedelta

from irrivise_core.aquacrop_adapter import evaluate_schedule
from irrivise_core.science import Weather


def test_aquacrop_full_season_schedule():
    start = date(2025, 6, 1)
    weather = [Weather((start + timedelta(days=i)).isoformat(), 2 if i % 7 == 0 else 0, 4.5, 22, 33) for i in range(180)]
    rainfed = evaluate_schedule(weather, [0] * 180)
    scheduled = evaluate_schedule(weather, [10 if i % 3 == 0 else 0 for i in range(180)])
    assert rainfed["aquacrop_seasonal_irrigation_mm"] == 0
    assert scheduled["aquacrop_seasonal_irrigation_mm"] > 0
    assert 0 <= rainfed["aquacrop_simulated_dry_yield_t_ha"] < 30
    assert 0 <= scheduled["aquacrop_simulated_dry_yield_t_ha"] < 30
