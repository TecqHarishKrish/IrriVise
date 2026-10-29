"""Generate (or verify) the deterministic SYNTHETIC offline weather fixture.

    python scripts/sample_data.py          # (re)write data/sample/synthetic_weather_tn_v1.csv + manifest
    python scripts/sample_data.py --check  # regenerate in memory and compare with the committed checksum
"""
import argparse
import json

import _bootstrap  # noqa: F401
from _bootstrap import ROOT

from irrivise_core.data.synthetic import GENERATOR_VERSION, generate_synthetic_weather
from irrivise_core.data.weather import read_weather_csv, write_weather_csv
from irrivise_core.util.repro import sha256_file

CSV = ROOT / "data" / "sample" / "synthetic_weather_tn_v1.csv"
MANIFEST = ROOT / "data" / "manifests" / "synthetic_weather_tn_v1.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    frame = generate_synthetic_weather(start_year=2004, years=20, latitude=10.79, seed=42)
    if args.check:
        tmp = ROOT / ".cache" / "sample_check.csv"
        write_weather_csv(frame, tmp)
        expected = json.loads(MANIFEST.read_text(encoding="utf-8"))["checksum_sha256"]
        actual = sha256_file(tmp)
        print(json.dumps({"expected": expected, "regenerated": actual, "match": expected == actual}))
        raise SystemExit(0 if expected == actual else 1)
    write_weather_csv(frame, CSV)
    _, report = read_weather_csv(CSV)
    manifest = {"file": str(CSV.relative_to(ROOT)), "checksum_sha256": sha256_file(CSV), "rows": report.rows, "start": report.start,
                "end": report.end, "generator": GENERATOR_VERSION, "seed": 42, "latitude": 10.79, "longitude": 78.70,
                "label": "SYNTHETIC DEMONSTRATION — generated weather, not historical observations or field measurements",
                "method": "Markov-chain rain occurrence + gamma amounts + year factor; Hargreaves ET0 (FAO-56 eq. 52)"}
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
