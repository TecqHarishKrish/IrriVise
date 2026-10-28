"""Printable HTML reports with inline SVG charts, generated only from saved artifacts."""
from __future__ import annotations

import html
import json
from datetime import datetime, timezone

LIMITATIONS = [
    "All farm outcomes are simulated. The reference farm is a hidden simulation, not a measured field.",
    "yield_proxy_t_ha is an FAO-33 stage yield-response proxy from the fast surrogate; it is not measured yield.",
    "AquaCrop values (when present) are AquaCrop-OSPy simulations of the applied schedule with default, uncalibrated parameters.",
    "CARAT regret and value of information are estimates under the twin's own model, not oracle quantities.",
    "Synthetic demonstration weather is generated, not historical; NASA POWER data are gridded estimates, not on-farm observations.",
]

STYLE = """
body{font-family:Inter,system-ui,sans-serif;color:#1d2939;margin:32px auto;max-width:960px;padding:0 20px;line-height:1.5}
h1{color:#123D34;margin-bottom:4px}h2{color:#123D34;border-bottom:1px solid #d0e2d9;padding-bottom:4px;margin-top:28px}
table{border-collapse:collapse;width:100%;font-size:13px;margin:8px 0}th,td{border:1px solid #d0d5dd;padding:5px 7px;text-align:left}
th{background:#E9F3EE}.note{background:#FAFAF7;border-left:3px solid #B76C23;padding:8px 12px;font-size:13px}
.badge{display:inline-block;background:#fdf2e3;color:#7a4510;border:1px solid #e9cfa9;border-radius:4px;padding:2px 8px;font-size:12px;font-weight:600}
figure{margin:12px 0}figcaption{font-size:12px;color:#475467}code{font-size:12px}
@media print{body{margin:0}h2{break-after:avoid}figure,table{break-inside:avoid}}
"""


def esc(value) -> str:
    return html.escape("—" if value is None else str(value))


def fmt(value, digits: int = 3) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return esc(value)


def svg_chart(series: list[dict], x: list[float], title: str, y_label: str, x_label: str = "Day of season", width: int = 860,
              height: int = 260, bars: list[dict] | None = None) -> str:
    """Minimal accessible SVG line/bar chart. series: {name, values, color, dash?}; bars: {name, values, color}."""
    pad_l, pad_r, pad_t, pad_b = 56, 16, 28, 40
    values = [v for s in series for v in s["values"] if v is not None] + [v for b in (bars or []) for v in b["values"] if v is not None]
    if not values or not x:
        return f"<p>{esc(title)}: no data</p>"
    lo, hi = min(0.0, min(values)), max(values)
    hi = hi if hi > lo else lo + 1
    x0, x1 = min(x), max(x)
    sx = lambda v: pad_l + (v - x0) / max(1e-9, x1 - x0) * (width - pad_l - pad_r)  # noqa: E731
    sy = lambda v: height - pad_b - (v - lo) / (hi - lo) * (height - pad_t - pad_b)  # noqa: E731
    parts = [f'<svg role="img" aria-label="{esc(title)}" viewBox="0 0 {width} {height}" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="sans-serif" font-size="11">',
             f'<title>{esc(title)}</title>']
    for i in range(5):
        v = lo + (hi - lo) * i / 4
        y = sy(v)
        parts.append(f'<line x1="{pad_l}" x2="{width - pad_r}" y1="{y:.1f}" y2="{y:.1f}" stroke="#e4e7ec"/><text x="{pad_l - 6}" y="{y + 4:.1f}" text-anchor="end" fill="#475467">{v:.1f}</text>')
    for i in range(6):
        v = x0 + (x1 - x0) * i / 5
        parts.append(f'<text x="{sx(v):.1f}" y="{height - pad_b + 16}" text-anchor="middle" fill="#475467">{v:.0f}</text>')
    bw = max(1.0, (width - pad_l - pad_r) / max(1, len(x)) * 0.8)
    for b in bars or []:
        for xv, v in zip(x, b["values"]):
            if v:
                parts.append(f'<rect x="{sx(xv) - bw / 2:.1f}" y="{sy(v):.1f}" width="{bw:.1f}" height="{max(0.0, sy(lo) - sy(v)):.1f}" fill="{b["color"]}" opacity="0.75"/>')
    for s in series:
        pts = " ".join(f"{sx(xv):.1f},{sy(v):.1f}" for xv, v in zip(x, s["values"]) if v is not None)
        dash = ' stroke-dasharray="5 4"' if s.get("dash") else ""
        parts.append(f'<polyline fill="none" stroke="{s["color"]}" stroke-width="1.8"{dash} points="{pts}"/>')
    legend = (series or []) + (bars or [])
    for i, item in enumerate(legend):
        parts.append(f'<rect x="{pad_l + i * 170}" y="8" width="10" height="10" fill="{item["color"]}"/><text x="{pad_l + 14 + i * 170}" y="17" fill="#344054">{esc(item["name"])}</text>')
    parts.append(f'<text x="{(width + pad_l) / 2}" y="{height - 6}" text-anchor="middle" fill="#344054">{esc(x_label)}</text>')
    parts.append(f'<text transform="translate(14 {height / 2}) rotate(-90)" text-anchor="middle" fill="#344054">{esc(y_label)}</text></svg>')
    return "".join(parts)


def _page(title: str, body: str, manifest: dict) -> str:
    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    limits = "".join(f"<li>{esc(x)}</li>" for x in LIMITATIONS)
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{esc(title)}</title><style>{STYLE}</style></head><body><h1>{esc(title)}</h1>"
            f"<p><span class='badge'>Simulated results — not field measurements</span> Generated {esc(generated)} by IrriVise from saved artifacts.</p>"
            f"{body}<h2>Limitations</h2><ul>{limits}</ul><h2>Reproducibility manifest</h2>"
            f"<pre style='white-space:pre-wrap;font-size:11px;background:#f9fafb;padding:10px'>{esc(json.dumps(manifest, indent=1, default=str)[:20000])}</pre>"
            f"</body></html>")


def run_report(run: dict, daily: list[dict], manifest: dict) -> str:
    s = run["summary"]
    aq = s.get("aquacrop") or {}
    x = [d["day"] for d in daily]
    kpis = [("Seasonal irrigation", f"{fmt(s['seasonal_irrigation_mm'], 1)} mm"), ("Seasonal rainfall", f"{fmt(s['seasonal_rain_mm'], 1)} mm"),
            ("Yield proxy (FAO-33, surrogate)", f"{fmt(s['yield_proxy_t_ha'], 2)} t/ha"),
            ("AquaCrop-simulated dry yield", f"{fmt(aq.get('aquacrop_simulated_dry_yield_t_ha'), 2)} t/ha" if "aquacrop_simulated_dry_yield_t_ha" in aq else esc(aq.get("error", "not evaluated"))),
            ("Irrigation water productivity (proxy)", f"{fmt(s['irrigation_wp_proxy_kg_m3'], 2)} kg/m³"),
            ("Cumulative water stress Σ(1−Ks)", fmt(s["cumulative_stress"], 2)), ("Stress days (Ks<1)", fmt(s["stress_days"])),
            ("Soil readings used", f"{s['observation_count']} (budget remaining {s['observations_remaining']})"),
            ("Twin RMSE vs simulated reference", f"{fmt(s['twin_rmse_mm'], 2)} mm ({fmt(s['twin_rmse_m3m3'], 4)} m³/m³)"),
            ("Mean estimated regret (model estimate)", fmt(s.get("estimated_regret_mean"), 4)),
            ("Hard-constraint violations", f"{s['max_daily_violations']} daily / {s['season_budget_violations']} seasonal")]
    rows = "".join(f"<tr><th>{esc(k)}</th><td>{v}</td></tr>" for k, v in kpis)
    soil = svg_chart([{"name": "Twin mean (estimate)", "values": [d["belief_mean_mm"] for d in daily], "color": "#168268"},
                      {"name": "Twin 10th pct", "values": [d["belief_q10_mm"] for d in daily], "color": "#8fc7b3", "dash": True},
                      {"name": "Twin 90th pct", "values": [d["belief_q90_mm"] for d in daily], "color": "#8fc7b3", "dash": True}],
                     x, "Estimated root-zone water storage", "Root-zone storage (mm)")
    water = svg_chart([], x, "Rainfall and applied irrigation", "Depth (mm/day)",
                      bars=[{"name": "Rain (mm/day)", "values": [d["rain_mm"] for d in daily], "color": "#7fb3d5"},
                            {"name": "Irrigation (mm/day)", "values": [d["applied_mm"] for d in daily], "color": "#168268"}])
    obs_days = [d for d in daily if d.get("observed")]
    obs_rows = "".join(f"<tr><td>{fmt(d['day'], 0)}</td><td>{esc(d['date'])}</td><td>{fmt(d.get('measurement_theta'), 4)}</td>"
                       f"<td>{fmt(d.get('belief_mean_mm'), 1)} → {fmt(d.get('corrected_mean_mm'), 1)}</td><td>{fmt(d.get('net_voi'), 4)}</td></tr>" for d in obs_days[:60])
    body = (f"<h2>Run</h2><table><tr><th>Method</th><td>{esc(run['method_label'])} ({esc(run['method_code'])})</td></tr>"
            f"<tr><th>Season / split</th><td>{esc(run['season_id'])} ({esc(run['split'])})</td></tr><tr><th>Seed</th><td>{esc(run['seed'])}</td></tr>"
            f"<tr><th>Run id</th><td><code>{esc(run['id'])}</code></td></tr></table>"
            f"<h2>Key results</h2><table>{rows}</table>"
            f"<figure>{soil}<figcaption>Figure 1. Twin estimate of root-zone water (mm) with 10–90% ensemble band. Source: daily.csv of this run.</figcaption></figure>"
            f"<figure>{water}<figcaption>Figure 2. Realized rainfall (dataset) and applied irrigation (mm/day). Source: daily.csv.</figcaption></figure>"
            f"<h2>Soil readings</h2>" + (f"<table><tr><th>Day</th><th>Date</th><th>θ reading (m³/m³)</th><th>Twin mean before → after (mm)</th><th>Net VOI</th></tr>{obs_rows}</table>"
                                        if obs_days else "<p>No soil readings were taken in this run.</p>"))
    return _page(f"IrriVise run report — {run['method_label']}", body, manifest)


def experiment_report(experiment: dict, manifest: dict) -> str:
    summary = experiment["summary"]
    metrics = [("seasonal_irrigation_mm", "Irrigation (mm)"), ("yield_proxy_t_ha", "Yield proxy (t/ha)"), ("aquacrop_yield_t_ha", "AquaCrop yield (t/ha)"),
               ("cumulative_stress", "Σ(1−Ks)"), ("observation_count", "Readings"), ("twin_rmse_mm", "Twin RMSE (mm)"),
               ("objective_with_observation_cost", "Objective")]
    head = "".join(f"<th>{esc(label)}</th>" for _, label in metrics)
    rows = ""
    for t in summary["table"]:
        cells = ""
        for key, _ in metrics:
            d = t.get(key) or {}
            if d.get("mean") is None:
                cells += "<td>—</td>"
            else:
                ci = d.get("ci95")
                cells += f"<td>{d['mean']:.3f}" + (f"<br><small>[{ci[0]:.3f}, {ci[1]:.3f}]</small>" if ci else "") + "</td>"
        rows += f"<tr><th>{esc(t['code'])} {esc(t['label'])}</th><td>{t['runs']} ({t['failed_runs']} failed)</td>{cells}</tr>"
    comp_rows = ""
    for method, comp in summary["paired_vs_reference"].items():
        for key in ("seasonal_irrigation_mm", "yield_proxy_t_ha", "cumulative_stress", "objective_with_observation_cost"):
            c = comp.get(key, {})
            if c.get("n_pairs"):
                ci = c.get("ci95")
                comp_rows += (f"<tr><td>{esc(method)}</td><td>{esc(key)}</td><td>{c['mean_difference']:+.3f}</td>"
                              f"<td>{'[%.3f, %.3f]' % tuple(ci) if ci else '—'}</td><td>{c['n_pairs']}</td><td>{esc(c.get('wilcoxon_p'))}</td><td>{esc(c['status'])}</td></tr>")
    narrative = "".join(f"<li>{esc(x)}</li>" for x in summary.get("narrative", []))
    cfg = summary["config"]
    body = (f"<h2>Design</h2><p>Split: <b>{esc(cfg['split'])}</b>; seeds {esc(cfg['seeds'])}; observation budgets {esc(cfg['observation_budgets'])}; "
            f"sensor noise {esc(cfg['sensor_noise_m3m3'])} m³/m³ ({esc(cfg['sensor_mode'])}); reference method <b>{esc(cfg['reference_method'])}</b>. "
            f"All methods were evaluated on identical cells with common random numbers.</p>"
            f"<h2>What did the data show?</h2><ul>{narrative}</ul>"
            f"<h2>Method summary (mean, bootstrap 95% CI)</h2><div style='overflow-x:auto'><table><tr><th>Method</th><th>Runs</th>{head}</tr>{rows}</table></div>"
            f"<h2>Paired differences vs reference</h2><table><tr><th>Method</th><th>Metric</th><th>Mean diff.</th><th>95% CI</th><th>n</th><th>Wilcoxon p</th><th>Status</th></tr>{comp_rows}</table>"
            f"<p class='note'>Failed runs: {summary['n_failed']}. Hard-constraint violations across all runs: {summary['hard_constraint_violations']}.</p>")
    return _page(f"IrriVise experiment report — {experiment['name']}", body, manifest)


def model_report(model: dict) -> str:
    m = model.get("manifest") or {}
    hist = m.get("history", [])
    x = [h["timesteps"] for h in hist]
    chart = svg_chart([{"name": "Validation mean reward", "values": [h.get("validation_mean_reward") for h in hist], "color": "#168268"},
                       {"name": "Train mean episode reward", "values": [h.get("train_mean_episode_reward") for h in hist], "color": "#B76C23", "dash": True}],
                      x, "PPO learning curve", "Episode reward (reward units)", x_label="Timesteps") if hist else "<p>No evaluation points were logged.</p>"
    body = (f"<h2>Model</h2><table><tr><th>Preset</th><td>{esc(model['preset'])}</td></tr><tr><th>Seed</th><td>{esc(model['seed'])}</td></tr>"
            f"<tr><th>Timesteps</th><td>{esc(model['actual_timesteps'])}</td></tr><tr><th>Checkpoint SHA-256</th><td><code>{esc(model['checkpoint_sha256'])}</code></td></tr>"
            f"<tr><th>Research quality preset</th><td>{esc(model['research_quality'])}</td></tr></table>"
            f"<figure>{chart}<figcaption>Figure 1. Logged training/validation rewards (simulated seasons).</figcaption></figure>")
    return _page("IrriVise model report", body, m)
