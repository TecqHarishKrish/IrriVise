"""Physical invariants of the daily root-zone water balance."""
import numpy as np
import pytest

from irrivise_core.simulation import water_balance as wb


def args(soil, storage, rain=0.0, irr=0.0, eto=5.0, zr0=0.5, zr1=0.5, kc=1.0):
    return dict(storage_mm=storage, theta_wp=soil.theta_wp, theta_fc=soil.theta_fc, theta_sat=soil.theta_sat, tau=soil.drainage_tau,
                curve_number=soil.curve_number, zr_prev=zr0, zr_next=zr1, rain_mm=rain, irrigation_mm=irr, eto_mm=eto, kc=kc, p=0.55,
                subsoil_fraction=0.7)


@pytest.mark.parametrize("rain,irr,eto", [(0, 0, 5), (300, 0, 2), (0, 20, 8), (45, 15, 0), (500, 100, 15)])
def test_mass_balance_closes_and_bounds_hold(scenario, rain, irr, eto):
    soil = scenario.soil
    for storage in (soil.theta_wp * 500, soil.theta_fc * 500, soil.theta_sat * 500):
        f = wb.step(**args(soil, storage, rain, irr, eto))
        assert abs(float(f.residual_mm)) < 1e-9
        assert soil.theta_wp * 500 - 1e-9 <= float(f.storage_mm) <= soil.theta_sat * 500 + 1e-9
        assert min(float(f.runoff_mm), float(f.actual_et_mm), float(f.drainage_mm)) >= 0
        assert float(f.actual_et_mm) <= float(f.crop_et_mm) + 1e-12


def test_saturation_excess_becomes_runoff_not_storage(scenario):
    soil = scenario.soil
    f = wb.step(**args(soil, soil.theta_sat * 500, rain=200, eto=0))
    assert float(f.runoff_mm) > 0 and float(f.storage_mm) <= soil.theta_sat * 500 + 1e-9


def test_root_growth_water_is_accounted(scenario):
    soil = scenario.soil
    f = wb.step(**args(soil, soil.theta_fc * 300, eto=0, zr0=0.3, zr1=0.35))
    assert float(f.root_expansion_mm) > 0 and abs(float(f.residual_mm)) < 1e-9


def test_dry_soil_stresses_and_et_stops_at_wilting(scenario):
    soil = scenario.soil
    f = wb.step(**args(soil, soil.theta_wp * 500, eto=8))
    assert float(f.ks) == pytest.approx(0.0) and float(f.actual_et_mm) == pytest.approx(0.0)


def test_rejects_invalid_inputs(scenario):
    soil = scenario.soil
    with pytest.raises(ValueError):
        wb.step(**args(soil, 100, rain=-1))
    with pytest.raises(ValueError):
        wb.step(**args(soil, float("nan")))
    with pytest.raises(ValueError):
        wb.step(**args(soil, 100, zr0=0.5, zr1=0.4))


def test_crop_calendar_progression(scenario):
    cal = wb.CropCalendar(scenario.crop)
    assert cal.stage(0) == 0 and cal.stage(cal.length - 1) == 3
    roots = [cal.root_depth(d) for d in range(cal.length + 1)]
    assert all(b >= a for a, b in zip(roots, roots[1:]))
    assert cal.kc(0) == scenario.crop.kc_ini and cal.kc(80) == scenario.crop.kc_mid


def test_yield_proxy_ratio_bounds():
    ky = (0.4, 0.4, 1.5, 0.5)
    assert wb.yield_proxy_ratio(np.array([10, 20, 30, 10.0]), np.array([10, 20, 30, 10.0]), ky) == 1.0
    assert wb.yield_proxy_ratio(np.zeros(4), np.ones(4), ky) == 0.0
    assert 0 < wb.yield_proxy_ratio(np.array([10, 20, 25, 10.0]), np.array([10, 20, 30, 10.0]), ky) < 1
