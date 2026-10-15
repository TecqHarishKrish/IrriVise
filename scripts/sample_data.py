"""Generate deterministic synthetic weather for an offline software demonstration."""
import csv
from datetime import date, timedelta
from math import sin, pi
from pathlib import Path
from random import Random

ROOT = Path(__file__).resolve().parents[1]


def generate(path: Path = ROOT / "data/sample/weather.csv", days: int = 150, seed: int = 42) -> Path:
    rng = Random(seed)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "rain_mm", "eto_mm", "tmin_c", "tmax_c"])
        for day in range(days):
            wet = rng.random() < (0.25 + 0.12 * sin(day * pi / 45))
            rain = round(rng.uniform(2, 23), 2) if wet else 0.0
            writer.writerow([(date(2025, 6, 1) + timedelta(days=day)).isoformat(), rain, round(4.2 + 0.6 * sin(day * pi / 40), 2), 22.0, 33.0])
    return path


if __name__ == "__main__":
    print(generate())
