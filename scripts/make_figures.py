"""Publication figures from recorded results and fresh simulation runs.

    python scripts/make_figures.py --out docs/figures

Figures 1-3 are drawn only from saved result files in docs/results/ (no number is
typed in by hand). Figures 4-5 re-run the simulator (no PPO needed) on held-out
test season 2020, seed 1 (the first test season and seed, not selected for effect).
Every figure is saved as PNG (300 dpi) and PDF (vector). All outcomes are simulated.
"""
import argparse
import json
import re

import _bootstrap  # noqa: F401
from _bootstrap import ROOT

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from irrivise_core.config import default_scenario  # noqa: E402
from irrivise_core.data.weather import chronological_split, extract_seasons, read_weather_csv  # noqa: E402
from irrivise_core.evaluation.runner import run_episode  # noqa: E402
from irrivise_core.simulation.forecast import ClimatologyForecaster  # noqa: E402

# Validated reference palette (dataviz skill, light mode), first three slots only.
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#8a8984", "#e6e5e0", "#ffffff"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9, "axes.titlesize": 10, "axes.titleweight": "bold",
    "axes.labelsize": 9, "axes.labelcolor": INK2, "axes.edgecolor": MUTED, "axes.linewidth": 0.8,
    "xtick.color": INK2, "ytick.color": INK2, "xtick.labelsize": 8, "ytick.labelsize": 8,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.6, "axes.axisbelow": True, "legend.frameon": False, "legend.fontsize": 8,
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "text.color": INK, "pdf.fonttype": 42,
})


def save(fig, out, name):
    for ext in ("png", "pdf"):
        fig.savefig(out / f"{name}.{ext}", dpi=300, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    print("wrote", name)


# ---------------------------------------------------------------- Figure 1
SHORT = {"fixed_schedule": "B0 Fixed schedule", "soil_threshold": "B1 Soil-moisture threshold", "ppo": "B2 PPO, no readings",
         "ppo_fixed_interval": "B3 PPO + fixed-interval readings", "ppo_random": "B4 PPO + random readings",
         "ppo_uncertainty": "B5 PPO + uncertainty-threshold", "ppo_carat_no_risk": "A5 CARAT, no soft risk layer",
         "ppo_carat_no_correction": "A6 CARAT, no twin correction", "carat_full": "P  Full CARAT (proposed)",
         "lookahead_carat": "P-noPPO  CARAT planner", "ppo_daily": "R  PPO + daily readings"}
PROPOSED = {"carat_full", "lookahead_carat"}


def fig_benchmark(out):
    table = json.loads((ROOT / "docs/results/main_benchmark.json").read_text(encoding="utf-8"))["summary"]["table"]
    rows = sorted(table, key=lambda r: r["yield_proxy_t_ha"]["mean"])
    fig, axes = plt.subplots(1, 3, figsize=(7.2, 3.6), sharey=True, gridspec_kw={"width_ratios": [1.25, 1, 0.75], "wspace": 0.08})
    y = np.arange(len(rows))
    for ax, key, title, unit in ((axes[0], "yield_proxy_t_ha", "(a) Yield proxy", "t/ha"),
                                 (axes[1], "seasonal_irrigation_mm", "(b) Seasonal irrigation", "mm"),
                                 (axes[2], "observation_count", "(c) Soil readings", "per season")):
        for i, r in enumerate(rows):
            st = r[key]
            color = BLUE if r["method"] in PROPOSED else MUTED
            lo, hi = st["ci95"]
            ax.plot([lo, hi], [i, i], color=color, lw=2, solid_capstyle="round")
            ax.plot(st["mean"], i, "o", ms=6, color=color, mec=SURFACE, mew=1.2, zorder=3)
        ax.set_title(title, loc="left")
        ax.set_xlabel(unit)
        ax.grid(axis="y", visible=False)
    axes[0].set_yticks(y, [SHORT[r["method"]] for r in rows])
    for lab, r in zip(axes[0].get_yticklabels(), rows):
        if r["method"] in PROPOSED:
            lab.set_fontweight("bold")
    axes[2].set_xscale("symlog", linthresh=10)
    axes[2].set_xticks([0, 5, 10, 140], ["0", "5", "10", "140"])
    fig.text(0.0, -0.04, "Mean and 95 % bootstrap CI over 20 matched cells (test seasons 2020–2023 × seeds 1–5), budget 10 readings, "
             "σ = 0.02 m³/m³. Simulated farm.", fontsize=7, color=INK2)
    save(fig, out, "fig1_main_benchmark")


# ---------------------------------------------------------------- Figure 2
def fig_robustness(out):
    md = (ROOT / "docs/results/robustness_breakdown.md").read_text(encoding="utf-8")
    num = r"([+-]?\d+\.\d+)"
    pat = re.compile(rf"^\| (\d+) \| (0\.0\d) \| [\d.]+ / [\d.]+ \| {num} \[{num}, {num}\]", re.M)
    rows = [(int(b), float(n), float(m), float(lo), float(hi)) for b, n, m, lo, hi in pat.findall(md)]
    assert len(rows) == 12, rows
    budgets, noises = [5, 10, 20, 40], [0.01, 0.02, 0.04]
    colors = dict(zip(noises, (BLUE, ORANGE, AQUA)))
    fig, ax = plt.subplots(figsize=(5.2, 3.0))
    for b, n, m, lo, hi in rows:
        x = budgets.index(b) + (noises.index(n) - 1) * 0.22
        ax.plot([x, x], [lo, hi], color=colors[n], lw=2, solid_capstyle="round")
        ax.plot(x, m, "o", ms=6, color=colors[n], mec=SURFACE, mew=1.2, zorder=3)
    ax.axhline(0, color=INK2, lw=0.9)
    ax.set_xticks(range(4), [f"{b} readings" for b in budgets])
    ax.set_ylabel("Δ total reward, CARAT − B3")
    ax.grid(axis="x", visible=False)
    for n in noises:
        ax.plot([], [], "o", color=colors[n], label=f"σ = {n} m³/m³")
    ax.legend(ncol=3, loc="upper left", bbox_to_anchor=(0, 1.12))
    fig.text(0.0, -0.06, "Paired difference (Full CARAT − PPO + fixed-interval readings), mean and 95 % CI, total reward excluding "
             "reading cost;\n4 test seasons × 3 seeds per cell. Simulated farm.", fontsize=7, color=INK2)
    save(fig, out, "fig2_robustness")


# ---------------------------------------------------------------- Figure 3
FAULT_LABEL = {"nominal": "Healthy\nsensor", "missing": "25 %\ndropout", "biased+": "+0.03\nwet bias", "biased-": "−0.03\ndry bias", "stuck": "Stuck\nsensor"}
HANDLING = (("none", "No bias handling", MUTED), ("innovation_monitor", "Innovation monitor", ORANGE), ("augmented", "Augmented offset state", BLUE))


def fig_sensor_bias(out):
    s = json.loads((ROOT / "docs/results/sensor_bias_nonppo_test.json").read_text(encoding="utf-8"))["summary"]
    faults = list(FAULT_LABEL)
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.0), sharey=True, gridspec_kw={"wspace": 0.06})
    w = 0.26
    for ax, planner, title in ((axes[0], "lookahead_carat", "(a) CARAT planner"), (axes[1], "soil_threshold", "(b) Soil-moisture threshold rule")):
        for j, (key, label, color) in enumerate(HANDLING):
            vals = [s[f"{f}|{key}|{planner}"]["yield_proxy_t_ha"] for f in faults]
            ax.bar(np.arange(5) + (j - 1) * w, [v - 7.5 for v in vals], width=w - 0.03, bottom=7.5, color=color, label=label)
        ax.axhline(s["nominal|none|fixed_schedule"]["yield_proxy_t_ha"], color=INK2, lw=0.9, ls=(0, (4, 3)),
                   label="B0 fixed schedule (no readings)")
        ax.set_xticks(range(5), [FAULT_LABEL[f] for f in faults])
        ax.set_title(title, loc="left")
        ax.grid(axis="x", visible=False)
        ax.set_ylim(7.5, 9.0)
    axes[0].set_ylabel("Yield proxy (t/ha), axis from 7.5")
    axes[0].legend(ncol=4, loc="upper left", bbox_to_anchor=(0, 1.22), handlelength=1.6, columnspacing=1.2)
    fig.text(0.0, -0.1, "Mean over 20 matched cells (test seasons 2020–2023 × seeds 1–5), budget 10 readings, σ = 0.02 m³/m³.\n"
             "Paired 95 % CIs in docs/results/sensor_bias_nonppo_test.md. Simulated farm.", fontsize=7, color=INK2)
    save(fig, out, "fig3_sensor_bias")


# ---------------------------------------------------------------- Figures 4-5 (fresh runs)
def setup():
    base = default_scenario(carat={"observation_cost": 0.0})
    frame, _ = read_weather_csv(ROOT / "data/sample/synthetic_weather_tn_v1.csv")
    seasons, _ = extract_seasons(frame, base.planting_mmdd, base.crop.season_length)
    split = chronological_split([s.season_id for s in seasons])
    forecaster = ClimatologyForecaster([s for s in seasons if s.season_id in split.train])
    season = next(s for s in seasons if s.season_id == split.test[0])
    return base, forecaster, season


def trace(scenario, season, forecaster):
    r = run_episode(scenario, season, forecaster, 1, "lookahead_carat", record_states=True)
    d, t = r.daily, r.truth
    day = np.array([x["day"] for x in d])
    true = np.array([x["true_storage_mm"] for x in t])
    est = np.array([x["end_belief_mean_mm"] for x in d])
    sd = np.array([x["end_belief_std_mm"] for x in d])
    obs = [(x["day"], x["measurement_theta"] * x["root_depth_m"] * 1000) for x in d if x["observed"] and x["measurement_theta"] is not None]
    return r, d, day, true, est, sd, obs


def soil_panel(ax, day, true, est, sd, obs, title):
    ax.fill_between(day, est - sd, est + sd, color=BLUE, alpha=0.18, lw=0, label="Twin ±1 sd")
    ax.plot(day, est, color=BLUE, lw=2, label="Twin estimate")
    ax.plot(day, true, color=INK, lw=1.2, ls=(0, (4, 2)), label="True soil water (hidden)")
    if obs:
        ox, oy = zip(*obs)
        ax.plot(ox, oy, "D", ms=6, color=ORANGE, mec=SURFACE, mew=1.2, zorder=4, label="Sensor reading")
    ax.set_title(title, loc="left")
    ax.set_ylabel("Root-zone water (mm)")


def fig_bias_trace(out, base, forecaster, season):
    biased = base.sensor.model_copy(update={"mode": "biased", "bias_m3m3": 0.03})
    fig, axes = plt.subplots(2, 1, figsize=(7.2, 4.6), sharex=True, sharey=True, gridspec_kw={"hspace": 0.32})
    for ax, method, title in ((axes[0], "none", "(a) No bias handling"), (axes[1], "augmented", "(b) Augmented sensor-offset state")):
        sc = base.model_copy(update={"sensor": biased, "twin_bias": base.twin_bias.model_copy(update={"method": method})})
        r, d, day, true, est, sd, obs = trace(sc, season, forecaster)
        soil_panel(ax, day, true, est, sd, obs, title)
        ax.set_ylim(0, 275)
        err = est - true
        ax.text(0.99, 0.04, f"twin >10 mm too wet on {int((err > 10).sum())} days, too dry on {int((err < -10).sum())} days · "
                f"irrigation {r.summary['seasonal_irrigation_mm']:.0f} mm · stress Σ(1−Ks) {r.summary['cumulative_stress']:.2f} · "
                f"yield proxy {r.summary['yield_proxy_t_ha']:.2f} t/ha", transform=ax.transAxes, ha="right", va="bottom", fontsize=7, color=INK2)
    axes[0].legend(ncol=4, loc="upper left", bbox_to_anchor=(0, 1.3))
    axes[1].set_xlabel("Day after planting")
    fig.text(0.0, -0.06, f"CARAT planner, sensor reading +0.03 m³/m³ too wet, test season {season.season_id}, seed 1, budget 10 readings. "
             "A twin that is too wet under-irrigates and\ncauses stress; (b) avoids this but runs slightly dry, the "
             "healthy-sensor cost discussed in METHODOLOGY §5.1. Simulated farm.", fontsize=7, color=INK2)
    save(fig, out, "fig4_bias_trace")


def fig_carat_season(out, base, forecaster, season):
    r, d, day, true, est, sd, obs = trace(base, season, forecaster)
    fig, axes = plt.subplots(3, 1, figsize=(7.2, 6.0), sharex=True, gridspec_kw={"height_ratios": [2.2, 1.2, 1], "hspace": 0.28})
    soil_panel(axes[0], day, true, est, sd, obs, "(a) Digital twin vs hidden truth")
    axes[0].legend(ncol=4, loc="upper left", bbox_to_anchor=(0, 1.3))
    voi = np.array([x["net_voi"] if x["net_voi"] is not None else np.nan for x in d])
    regret = np.array([x["est_regret"] for x in d])
    axes[1].plot(day, regret, color=INK2, lw=1.2, label="Estimated regret")
    axes[1].plot(day, voi, color=BLUE, lw=2, label="Net value of information")
    axes[1].axhline(0, color=INK2, lw=0.8)
    for x, _ in obs:
        axes[1].axvline(x, ymax=0.66, color=ORANGE, lw=1, alpha=0.7)
    axes[1].plot([], [], color=ORANGE, lw=1, label="Reading taken (net VOI > 0)")
    axes[1].set_title("(b) CARAT reading decision", loc="left")
    axes[1].set_ylabel("Reward units")
    axes[1].set_ylim(top=0.15)
    axes[1].legend(ncol=3, loc="upper left", fontsize=7)
    rain = np.array([x["rain_mm"] for x in d])
    irr = np.array([x["applied_mm"] for x in d])
    axes[2].bar(day, rain, width=0.9, color=MUTED, label="Rain")
    axes[2].bar(day, -irr, width=0.9, color=AQUA, label="Irrigation (plotted downward)")
    axes[2].axhline(0, color=INK2, lw=0.8)
    axes[2].set_title("(c) Water inputs", loc="left")
    axes[2].set_ylabel("mm/day")
    axes[2].set_xlabel("Day after planting")
    axes[2].set_ylim(top=115)
    axes[2].legend(ncol=2, loc="upper left", fontsize=7)
    fig.text(0.0, -0.02, f"CARAT planner, healthy sensor, test season {season.season_id}, seed 1: {r.summary['observation_count']} of 10 readings used, "
             f"{r.summary['seasonal_irrigation_mm']:.0f} mm irrigation, yield proxy {r.summary['yield_proxy_t_ha']:.2f} t/ha.\n"
             "When estimated regret is 0, net VOI equals minus the budget shadow price, hence the straight segments. Simulated farm.",
             fontsize=7, color=INK2)
    save(fig, out, "fig5_carat_season")
    return r


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="docs/figures")
    out = ROOT / ap.parse_args().out
    out.mkdir(parents=True, exist_ok=True)
    fig_benchmark(out)
    fig_robustness(out)
    fig_sensor_bias(out)
    base, forecaster, season = setup()
    fig_bias_trace(out, base, forecaster, season)
    fig_carat_season(out, base, forecaster, season)


if __name__ == "__main__":
    main()
