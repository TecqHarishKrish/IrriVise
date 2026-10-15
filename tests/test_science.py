from pathlib import Path
import pytest
from irrivise_core.data import load_weather
from irrivise_core.science import Soil, Weather, carat_decision, correct_belief, simulate, water_step


ROOT = Path(__file__).resolve().parents[1]


def test_mass_balance_and_saturation():
    soil = Soil()
    flux = water_step(soil.mm(soil.field_capacity), 200, 0, 4, soil)
    assert abs(flux.residual_mm) < 1e-8
    assert soil.mm(soil.wilting) <= flux.next_storage_mm <= soil.mm(soil.saturation)
    assert flux.runoff_mm > 0


def test_reject_bad_weather():
    with pytest.raises(ValueError):
        Weather("2025-01-01", float("nan"), 4, 20, 30)
    with pytest.raises(ValueError):
        Weather("2025-01-01", -1, 4, 20, 30)


def test_belief_correction():
    mean, variance = correct_belief(100, 100, 110, 25)
    assert mean == 108
    assert variance == pytest.approx(20)
    assert correct_belief(100, 0, 110, 0) == (100, 0)


def test_carat_agreement_skips_observation():
    soil = Soil()
    forecast = Weather("2025-01-01", 0, 4, 20, 30)
    result = carat_decision(soil.mm(soil.field_capacity), 0, soil, forecast, [0, 5], 10, 12, 42)
    assert result["regret_before"] == pytest.approx(0)
    assert not result["observe"]


def test_deterministic_budget_and_no_observation():
    weather = load_weather(ROOT / "data/sample/weather.csv")
    left, a = simulate(weather, Soil(), 0, 20, 0, "carat", 42)
    right, b = simulate(weather, Soil(), 0, 20, 0, "carat", 42)
    assert left == right and a == b
    assert a["seasonal_irrigation_mm"] == 0
    assert a["observations_used"] == 0
    assert all(row["irrigation_mm"] == 0 for row in left)


def test_invalid_empty_csv(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("date,rain_mm,eto_mm,tmin_c,tmax_c\n")
    with pytest.raises(ValueError, match="empty"):
        load_weather(path)


def test_duplicate_date_csv(tmp_path):
    path = tmp_path / "duplicate.csv"
    path.write_text("date,rain_mm,eto_mm,tmin_c,tmax_c\n2025-01-01,0,4,20,30\n2025-01-01,0,4,20,30\n")
    with pytest.raises(ValueError, match="daily"):
        load_weather(path)
