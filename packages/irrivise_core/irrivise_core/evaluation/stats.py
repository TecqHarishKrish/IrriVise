"""Paired statistics for matched comparisons (same season × seed × budget × noise).

Reports mean paired difference, a seeded percentile bootstrap 95% CI and a
Wilcoxon signed-rank p-value when enough non-zero pairs exist. Small samples
are flagged explicitly; nothing here claims significance on its own.
"""
from __future__ import annotations

import numpy as np

MIN_PAIRS_FOR_CI = 5


def bootstrap_ci(values: np.ndarray, seed: int = 12345, resamples: int = 4000, level: float = 0.95) -> tuple[float, float] | None:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) < MIN_PAIRS_FOR_CI:
        return None
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(values), size=(resamples, len(values)))
    means = values[idx].mean(axis=1)
    alpha = (1 - level) / 2
    return float(np.quantile(means, alpha)), float(np.quantile(means, 1 - alpha))


def describe(values) -> dict:
    v = np.asarray([x for x in values if x is not None and np.isfinite(x)], dtype=float)
    if len(v) == 0:
        return {"n": 0, "mean": None, "std": None, "ci95": None}
    ci = bootstrap_ci(v)
    return {"n": int(len(v)), "mean": float(v.mean()), "std": float(v.std(ddof=1)) if len(v) > 1 else 0.0,
            "min": float(v.min()), "max": float(v.max()), "ci95": list(ci) if ci else None}


def paired_difference(method: list[float | None], reference: list[float | None], higher_is_better: bool) -> dict:
    pairs = [(m, r) for m, r in zip(method, reference) if m is not None and r is not None and np.isfinite(m) and np.isfinite(r)]
    n = len(pairs)
    if n == 0:
        return {"n_pairs": 0, "status": "no paired data"}
    diff = np.array([m - r for m, r in pairs])
    ci = bootstrap_ci(diff)
    out = {"n_pairs": n, "mean_difference": float(diff.mean()), "median_difference": float(np.median(diff)),
           "ci95": list(ci) if ci else None, "wins": int(np.sum(diff > 1e-9) if higher_is_better else np.sum(diff < -1e-9)),
           "losses": int(np.sum(diff < -1e-9) if higher_is_better else np.sum(diff > 1e-9)), "ties": int(np.sum(np.abs(diff) <= 1e-9))}
    nonzero = diff[np.abs(diff) > 1e-12]
    if len(nonzero) >= 6:
        from scipy.stats import wilcoxon
        out["wilcoxon_p"] = float(wilcoxon(nonzero).pvalue)
    else:
        out["wilcoxon_p"] = None
    if n < MIN_PAIRS_FOR_CI:
        out["status"] = f"insufficient sample (n={n} < {MIN_PAIRS_FOR_CI}); descriptive only"
    elif ci is None:
        out["status"] = "CI unavailable"
    else:
        lo, hi = ci
        better = (lo > 0) if higher_is_better else (hi < 0)
        worse = (hi < 0) if higher_is_better else (lo > 0)
        out["status"] = "better (CI excludes 0)" if better else "worse (CI excludes 0)" if worse else "inconclusive (CI includes 0)"
    return out
