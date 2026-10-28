PY := .venv/bin/python
export PYTHONPATH := $(CURDIR)/packages/irrivise_core:$(CURDIR)/services/api
export MPLCONFIGDIR := $(CURDIR)/.cache/matplotlib

.PHONY: setup dev test test-web e2e smoke train-quick experiment

setup: ; ./scripts/setup.sh
dev: ; ./scripts/dev.sh
test: ; $(PY) -m pytest -q
test-web: ; cd apps/web && npm run lint && npm run typecheck && npx vitest run && npm run build
e2e: ; cd apps/web && npx playwright test
smoke: ; ./scripts/smoke_test.sh
train-quick: ; $(PY) scripts/train_ppo.py --preset cpu_quick --dataset sample --seed 42
experiment: ; $(PY) scripts/run_experiment.py --config configs/experiments/baselines.yaml
