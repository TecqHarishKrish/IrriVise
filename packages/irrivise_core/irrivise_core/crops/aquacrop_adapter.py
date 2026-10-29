"""AquaCrop-OSPy evaluation of PRECOMPUTED per-season irrigation schedules.

Design decision (see METHODOLOGY.md §AquaCrop): decisions are made on the
fast water-balance surrogate; the applied daily schedule is then replayed in
AquaCrop-OSPy (``IrrigationManagement(irrigation_method=3, Schedule=...)``)
to obtain an AQUACROP-SIMULATED dry yield. AquaCrop does not see the
surrogate's hidden state, and the decisions are not re-optimised inside
AquaCrop. Interactive step-wise action injection was not used because
mid-run schedule edits are not a documented, tested API.

Outputs are labelled "AquaCrop-simulated", never measured.
"""
from __future__ import annotations

from datetime import date, timedelta
from math import isfinite

import pandas as pd

SOIL_NAMES = {"sandy_loam": "SandyLoam", "loam": "Loam", "clay_loam": "ClayLoam"}
CROP_NAMES = {"maize": "Maize"}
SIMULATION_DAYS = 200  # weather window after planting so AquaCrop can reach maturity


class AquaCropUnavailable(RuntimeError):
    pass


def available() -> tuple[bool, str]:
    try:
        from importlib.metadata import version

        import aquacrop  # noqa: F401
        return True, version("aquacrop")
    except Exception as exc:  # pragma: no cover - environment dependent
        return False, f"{type(exc).__name__}: {exc}"


def evaluate_schedule(weather: pd.DataFrame, planting: str, schedule_mm: list[float], soil_profile: str = "sandy_loam",
                      crop: str = "maize") -> dict:
    """Run one AquaCrop season.

    ``weather`` must use the core schema and cover ``planting`` onwards;
    ``schedule_mm[i]`` is the irrigation applied ``i`` days after planting.
    """
    ok, info = available()
    if not ok:
        raise AquaCropUnavailable(f"aquacrop is not importable: {info}")
    if soil_profile not in SOIL_NAMES or crop not in CROP_NAMES:
        raise ValueError("No AquaCrop mapping for this soil/crop profile")
    if any((not isfinite(x)) or x < 0 or x > 100 for x in schedule_mm):
        raise ValueError("Irrigation schedule must contain finite depths in [0, 100] mm")
    import logging

    from aquacrop import AquaCropModel, Crop, InitialWaterContent, IrrigationManagement, Soil

    logging.getLogger("aquacrop").setLevel(logging.ERROR)
    start = date.fromisoformat(planting)
    frame = weather.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    window = frame[(frame["date"] >= pd.Timestamp(start)) & (frame["date"] < pd.Timestamp(start + timedelta(days=SIMULATION_DAYS)))]
    if len(window) < len(schedule_mm) + 30:
        raise ValueError("Not enough weather after planting for AquaCrop to reach maturity (need season + 30 days)")
    expected = pd.date_range(window["date"].iloc[0], window["date"].iloc[-1], freq="D")
    if len(expected) != len(window):
        raise ValueError("AquaCrop weather window has gaps")
    wdf = pd.DataFrame({"MinTemp": window["tmin_c"].to_numpy(), "MaxTemp": window["tmax_c"].to_numpy(),
                        "Precipitation": window["rain_mm"].to_numpy(), "ReferenceET": window["eto_mm"].to_numpy(),
                        "Date": window["date"].to_numpy()})
    days = [start + timedelta(days=i) for i, mm in enumerate(schedule_mm) if mm > 0]
    depths = [float(mm) for mm in schedule_mm if mm > 0]
    if depths:
        sched = pd.DataFrame({"Date": pd.to_datetime(days), "Depth": depths})
        irrigation = IrrigationManagement(irrigation_method=3, Schedule=sched, MaxIrr=max(depths) + 1.0)
    else:
        irrigation = IrrigationManagement(irrigation_method=0)
    sim_end = window["date"].iloc[-1].date()
    model = AquaCropModel(start.strftime("%Y/%m/%d"), sim_end.strftime("%Y/%m/%d"), wdf, Soil(SOIL_NAMES[soil_profile]),
                          Crop(CROP_NAMES[crop], planting_date=start.strftime("%m/%d")), InitialWaterContent(value=["FC"]), irrigation)
    model.run_model(till_termination=True)
    result = model.get_simulation_results()
    if result is None or len(result) == 0:
        raise ValueError("AquaCrop did not reach harvest inside the weather window")
    row = result.iloc[0]
    yield_t_ha = float(row["Dry yield (tonne/ha)"])
    irrigation_mm = float(row["Seasonal irrigation (mm)"])
    if not (isfinite(yield_t_ha) and isfinite(irrigation_mm)) or yield_t_ha < 0 or yield_t_ha > 30:
        raise ArithmeticError("Non-finite or implausible AquaCrop output")
    return {"aquacrop_simulated_dry_yield_t_ha": round(yield_t_ha, 4), "aquacrop_seasonal_irrigation_mm": round(irrigation_mm, 3),
            "schedule_irrigation_mm": round(sum(schedule_mm), 3), "harvest_date": str(row.get("Harvest Date (YYYY/MM/DD)", "")),
            "aquacrop_version": info, "soil": SOIL_NAMES[soil_profile], "crop": CROP_NAMES[crop], "initial_water_content": "FC",
            "label": "AquaCrop-OSPy simulated yield for a precomputed schedule (default crop/soil parameters; not calibrated, not measured)"}
