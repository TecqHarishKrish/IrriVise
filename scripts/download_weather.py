"""Download bounded historical NASA POWER daily weather into local cache."""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/irrivise_core"))
from irrivise_core.nasa_power import download_power

parser = argparse.ArgumentParser()
parser.add_argument("--latitude", type=float, required=True)
parser.add_argument("--longitude", type=float, required=True)
parser.add_argument("--start", type=date.fromisoformat, required=True)
parser.add_argument("--end", type=date.fromisoformat, required=True)
parser.add_argument("--time-standard", choices=["UTC", "LST"], default="UTC")
args = parser.parse_args()
print(json.dumps(download_power(args.latitude, args.longitude, args.start, args.end, args.time_standard, ROOT), indent=2))
