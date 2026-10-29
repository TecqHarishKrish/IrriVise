"""Repository-level integration: documented CLI commands run end to end."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args):
    return subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=600)


def test_sample_data_checksum_matches_committed_fixture():
    out = run("scripts/sample_data.py", "--check")
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout.strip().splitlines()[-1])["match"] is True


def test_cli_experiment_runs_and_writes_manifest():
    out = run("scripts/run_experiment.py", "--config", "configs/experiments/smoke.yaml")
    assert out.returncode == 0, out.stderr[-2000:]
    saved = out.stdout.strip().splitlines()[-1].replace("Saved to ", "")
    folder = ROOT / saved
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    assert summary["n_runs"] == 3 * 4 * 2 and summary["hard_constraint_violations"] == 0
    assert manifest["split"]["test"] == ["2020", "2021", "2022", "2023"] and manifest["dataset_sha256"]
