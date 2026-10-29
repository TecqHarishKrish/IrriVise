import sys, numpy as np
sys.path[:0] = ["/home/claude/irrivise/packages/irrivise_core", "/home/claude/irrivise/packages/irrivise_core/tests"]
import conftest as c, test_twin_bias as t
from irrivise_core.config import default_scenario
from irrivise_core.data.weather import *
from irrivise_core.simulation.forecast import ClimatologyForecaster
from irrivise_core.simulation.world import FieldWorld
sc = default_scenario(); df, _ = read_weather_csv(c.SAMPLE); ss, _ = extract_seasons(df, sc.planting_mmdd, sc.crop.season_length)
sp = chronological_split([s.season_id for s in ss]); fc = ClimatologyForecaster([s for s in ss if s.season_id in sp.train])
n = sc.model_copy(update={'observation_budget': 30})
for m in ['none', 'augmented']:
    w = FieldWorld(t.with_bias(n, method=m), ss[int(sys.argv[1])], fc, 1); last = None
    print(m)
    while not w.done:
        if w.day % 7 == 3:
            pre = w.twin.summary().mean_storage_mm
            meas, d = w.observe()
            print(f"day {w.day:3d} innov={d['innovation_mm']:6.1f} gain={d['gain']:.2f} bias={d.get('posterior_bias_m3m3', 0):+.4f} clip={d['clipped_members']:2d} "
                  f"err_before={pre - last:+5.1f} err_after={w.twin.summary().mean_storage_mm - last:+5.1f}")
        f = w.apply(5.0 if w.day % 3 == 0 else 0.0); last = f.storage_mm
