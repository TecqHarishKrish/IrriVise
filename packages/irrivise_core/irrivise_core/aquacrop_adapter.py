"""AquaCrop-OSPy season evaluation for precomputed irrigation schedules.

This adapter does not inject decisions during an active model run. It accepts
the complete schedule after a controller simulation and reports AquaCrop-
simulated yield, separate from the training surrogate's proxy.
"""
from __future__ import annotations

from datetime import date
from math import isfinite
from .science import Weather


def evaluate_schedule(weather: list[Weather], schedule_mm: list[float]) -> dict:
    """Evaluate one full maize season using AquaCrop 3.1's schedule interface."""
    if len(weather) != len(schedule_mm) or len(weather) < 96:
        raise ValueError("AquaCrop maize evaluation needs at least 96 matching daily records")
    if any(not isfinite(x) or x < 0 or x > 100 for x in schedule_mm):
        raise ValueError("Irrigation schedule must contain finite depths in [0,100] mm")
    import pandas as pd
    from aquacrop import AquaCropModel, Soil, Crop, InitialWaterContent, IrrigationManagement

    frame = pd.DataFrame({
        "MinTemp": [w.tmin_c for w in weather],
        "MaxTemp": [w.tmax_c for w in weather],
        "Precipitation": [w.rain_mm for w in weather],
        "ReferenceET": [w.eto_mm for w in weather],
        "Date": pd.to_datetime([w.date for w in weather]),
    })
    scheduled = pd.DataFrame({"Date": frame.loc[[i for i, mm in enumerate(schedule_mm) if mm > 0], "Date"], "Depth": [mm for mm in schedule_mm if mm > 0]})
    irrigation = IrrigationManagement(irrigation_method=3, Schedule=scheduled, MaxIrr=100.0, MaxIrrSeason=float(sum(schedule_mm))) if len(scheduled) else IrrigationManagement(irrigation_method=0)
    first = date.fromisoformat(weather[0].date)
    start = first.strftime("%Y/%m/%d")
    end = date.fromisoformat(weather[-1].date).strftime("%Y/%m/%d")
    model = AquaCropModel(start, end, frame, Soil("SandyLoam"), Crop("Maize", planting_date=first.strftime("%m/%d")), InitialWaterContent(value=["FC"]), irrigation)
    model.run_model(till_termination=True)
    result = model.get_simulation_results()
    if result.empty:
        raise ValueError("AquaCrop did not reach a harvest; extend weather coverage")
    crop = result.iloc[0]
    yield_t_ha = float(crop["Dry yield (tonne/ha)"])
    water_mm = float(crop["Seasonal irrigation (mm)"])
    if not isfinite(yield_t_ha) or not isfinite(water_mm):
        raise ArithmeticError("Non-finite AquaCrop output")
    return {"aquacrop_simulated_dry_yield_t_ha": yield_t_ha, "aquacrop_seasonal_irrigation_mm": water_mm, "harvest_date": str(crop["Harvest Date (YYYY/MM/DD)"]), "model": "AquaCrop-OSPy 3.1.0", "weather_source": "caller-supplied; validate provenance separately"}
