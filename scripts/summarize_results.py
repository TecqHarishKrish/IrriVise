"""Render saved experiment JSON (GET /api/v1/experiments/{id}) as Markdown tables.

    python scripts/summarize_results.py docs/results/main_benchmark.json > docs/results/main_benchmark.md

Every number is copied from the saved summary; nothing is recomputed or rounded beyond display.
"""
import json
import sys
from pathlib import Path

COLUMNS = [("seasonal_irrigation_mm", "Irrigation (mm)", 1), ("yield_proxy_t_ha", "Yield proxy (t/ha)", 2),
           ("aquacrop_yield_t_ha", "AquaCrop yield (t/ha)", 2), ("cumulative_stress", "Σ(1−Ks)", 2), ("observation_count", "Readings", 1),
           ("twin_rmse_mm", "Twin RMSE (mm)", 1), ("objective_with_observation_cost", "Objective", 2)]
PAIRED = [("seasonal_irrigation_mm", 1), ("yield_proxy_t_ha", 3), ("cumulative_stress", 2), ("objective_with_observation_cost", 3)]


def cell(stat: dict | None, digits: int) -> str:
    if not stat or stat.get("mean") is None:
        return "—"
    ci = stat.get("ci95")
    return f"{stat['mean']:.{digits}f}" + (f" [{ci[0]:.{digits}f}, {ci[1]:.{digits}f}]" if ci else "")


def render(path: Path) -> str:
    exp = json.loads(path.read_text(encoding="utf-8"))
    s, cfg = exp["summary"], exp["config"]
    out = [f"## {exp['name']}", "",
           f"Experiment `{exp['id']}` · split **{cfg['split']}** · seeds {cfg['seeds']} · observation budgets {cfg['observation_budgets']} · "
           f"sensor noise {cfg['sensor_noise_m3m3']} m³/m³ ({cfg['sensor_mode']}) · reference **{cfg['reference_method']}** · "
           f"{s['n_runs']} runs, {s['n_failed']} failed, {s['hard_constraint_violations']} hard-constraint violations.", "",
           "Mean [bootstrap 95% CI] over matched cells:", "",
           "| Code | Method | n | " + " | ".join(c[1] for c in COLUMNS) + " |", "|" + "---|" * (3 + len(COLUMNS))]
    for t in s["table"]:
        out.append(f"| {t['code']} | {t['label']} | {t['runs']} | " + " | ".join(cell(t.get(k), d) for k, _, d in COLUMNS) + " |")
    out += ["", f"Paired differences (method − {cfg['reference_method']}), mean [95% CI], status:", "",
            "| Method | " + " | ".join(k for k, _ in PAIRED) + " |", "|" + "---|" * (1 + len(PAIRED))]
    for method, comp in s["paired_vs_reference"].items():
        cells = []
        for key, d in PAIRED:
            c = comp.get(key, {})
            ci = c.get("ci95")
            cells.append(f"{c.get('mean_difference', 0):+.{d}f}" + (f" [{ci[0]:+.{d}f}, {ci[1]:+.{d}f}]" if ci else "") + f" — {c.get('status', '')}")
        out.append(f"| {method} | " + " | ".join(cells) + " |")
    out += ["", "What the data showed (generated):", ""] + [f"- {line}" for line in s["narrative"]] + [""]
    return "\n".join(out)


if __name__ == "__main__":
    print("\n".join(render(Path(p)) for p in sys.argv[1:]))
