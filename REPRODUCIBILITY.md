# Reproducibility

The sample generator is deterministic at seed 42. To regenerate its weather file:

```bash
PYTHONPATH=packages/irrivise_core .venv/bin/python scripts/sample_data.py
```

The API simulation request records controller, scenario, and seed in SQLite. Saved runs contain daily values, a sample dataset checksum, surrogate summary, and AquaCrop-simulated yield. To repeat a run, create the same scenario and submit the same controller and seed. The sample dataset checksum is exposed at `/api/v1/datasets`. Quick PPO manifests include seed, dataset and checkpoint SHA-256, actual step count, and a save/load inference check.

Tests:

```bash
PYTHONPATH=packages/irrivise_core:services/api .venv/bin/python -m pytest tests -q
```

This version lacks immutable per-run manifests containing code revision and dependency checksums; it also lacks split historical seasons and matched multi-seed experiments. A saved trace is reproducible only while code, dependency versions, and the generated sample file are unchanged. The quick PPO checkpoint is a functional artifact, not a selected or evaluated research model.
