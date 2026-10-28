import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".cache" / "matplotlib"))

from irrivise_core.config import default_scenario  # noqa: E402
from irrivise_core.data.weather import chronological_split, extract_seasons, read_weather_csv  # noqa: E402
from irrivise_core.simulation.forecast import ClimatologyForecaster  # noqa: E402

SAMPLE = ROOT / "data" / "sample" / "synthetic_weather_tn_v1.csv"


@pytest.fixture(scope="session")
def frame():
    df, _ = read_weather_csv(SAMPLE)
    return df


@pytest.fixture(scope="session")
def scenario():
    return default_scenario()


@pytest.fixture(scope="session")
def seasons(frame, scenario):
    s, _ = extract_seasons(frame, scenario.planting_mmdd, scenario.crop.season_length)
    return s


@pytest.fixture(scope="session")
def split(seasons):
    return chronological_split([s.season_id for s in seasons])


@pytest.fixture(scope="session")
def train(seasons, split):
    return [s for s in seasons if s.season_id in split.train]


@pytest.fixture(scope="session")
def forecaster(train):
    return ClimatologyForecaster(train)
