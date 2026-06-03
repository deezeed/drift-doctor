from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd


class Severity(str, Enum):
    OK = "ok"
    WARN = "warn"
    CRITICAL = "critical"


_SEVERITY_ORDER = {Severity.CRITICAL: 0, Severity.WARN: 1, Severity.OK: 2}

# Short display names used by the reporter table.
METRIC_LABELS = {
    "column_presence": "schema",
    "dtype": "dtype",
    "null_pct": "null%",
    "psi": "PSI",
    "js_divergence": "JS-div",
}


@dataclass
class DriftFinding:
    column: str
    metric: str
    severity: Severity
    reference_value: Any
    current_value: Any
    delta: float | None
    description: str
    detail: str = field(default="")   # pre-formatted one-liner for the reporter table


def _psi_severity(psi: float, warn: float = 0.1, crit: float = 0.25) -> Severity:
    if psi < warn:
        return Severity.OK
    if psi < crit:
        return Severity.WARN
    return Severity.CRITICAL


def _js_severity(js: float, warn: float = 0.1, crit: float = 0.3) -> Severity:
    if js < warn:
        return Severity.OK
    if js < crit:
        return Severity.WARN
    return Severity.CRITICAL


def _null_severity(delta: float, warn: float = 0.05, crit: float = 0.15) -> Severity:
    abs_d = abs(delta)
    if abs_d < warn:
        return Severity.OK
    if abs_d < crit:
        return Severity.WARN
    return Severity.CRITICAL


def compute_psi(
    ref_edges: list[float],
    ref_proportions: list[float],
    current_series: pd.Series,
) -> float | None:
    non_null = current_series.dropna()
    if len(non_null) == 0 or ref_edges is None:
        return None

    # Clip to reference range so out-of-range values fall into edge bins.
    clipped = non_null.clip(ref_edges[0], ref_edges[-1])
    counts, _ = np.histogram(clipped, bins=ref_edges)
    if counts.sum() == 0:
        return None

    cur_props = counts / counts.sum()
    eps = 1e-6
    psi = sum(
        (c - r) * np.log((c + eps) / (r + eps))
        for c, r in zip(cur_props, ref_proportions)
    )
    return float(max(0.0, psi))


def compute_js_divergence(ref_top_values: dict, current_series: pd.Series) -> float:
    cur_counts = current_series.value_counts(normalize=True, dropna=True)
    cur_counts.index = cur_counts.index.astype(str)

    all_cats = sorted(set(ref_top_values.keys()) | set(cur_counts.index))
    ref_dist = np.array([ref_top_values.get(c, 0.0) for c in all_cats])
    cur_dist = np.array([float(cur_counts.get(c, 0.0)) for c in all_cats])

    # "other" bucket captures mass not covered by top-k
    ref_dist = np.append(ref_dist, max(0.0, 1.0 - float(ref_dist.sum())))
    cur_dist = np.append(cur_dist, max(0.0, 1.0 - float(cur_dist.sum())))

    ref_dist = ref_dist / ref_dist.sum() if ref_dist.sum() > 0 else ref_dist
    cur_dist = cur_dist / cur_dist.sum() if cur_dist.sum() > 0 else cur_dist

    m = 0.5 * (ref_dist + cur_dist)
    eps = 1e-10
    js = 0.5 * np.sum(ref_dist * np.log((ref_dist + eps) / (m + eps))) + \
         0.5 * np.sum(cur_dist * np.log((cur_dist + eps) / (m + eps)))
    return float(np.clip(js, 0.0, 1.0))


def _js_divergence_from_dicts(top_a: dict, top_b: dict) -> float:
    all_cats = sorted(set(top_a.keys()) | set(top_b.keys()))
    ref_dist = np.array([top_a.get(c, 0.0) for c in all_cats])
    cur_dist = np.array([top_b.get(c, 0.0) for c in all_cats])
    ref_dist = np.append(ref_dist, max(0.0, 1.0 - float(ref_dist.sum())))
    cur_dist = np.append(cur_dist, max(0.0, 1.0 - float(cur_dist.sum())))
    ref_dist = ref_dist / ref_dist.sum() if ref_dist.sum() > 0 else ref_dist
    cur_dist = cur_dist / cur_dist.sum() if cur_dist.sum() > 0 else cur_dist
    m = 0.5 * (ref_dist + cur_dist)
    eps = 1e-10
    js = 0.5 * np.sum(ref_dist * np.log((ref_dist + eps) / (m + eps))) + \
         0.5 * np.sum(cur_dist * np.log((cur_dist + eps) / (m + eps)))
    return float(np.clip(js, 0.0, 1.0))


def _mean_shift_severity(delta_mean: float, ref_std: float) -> Severity:
    if ref_std == 0:
        return Severity.OK
    ratio = abs(delta_mean) / ref_std
    if ratio < 0.5:
        return Severity.OK
    if ratio < 1.5:
        return Severity.WARN
    return Severity.CRITICAL


def diff_profiles(
    profile_a: dict,
    profile_b: dict,
    skip_columns: set[str] | None = None,
) -> list[DriftFinding]:
    """Compare two snapshot profiles directly — no raw data needed."""
    skip = skip_columns or set()
    findings: list[DriftFinding] = []
    cols_a = set(profile_a["columns"].keys()) - skip
    cols_b = set(profile_b["columns"].keys()) - skip

    for col in cols_a - cols_b:
        findings.append(DriftFinding(
            column=col, metric="column_presence", severity=Severity.CRITICAL,
            reference_value="present", current_value="missing", delta=None,
            description=f"Column '{col}' missing in snapshot B",
            detail="present -> missing",
        ))

    for col in cols_b - cols_a:
        findings.append(DriftFinding(
            column=col, metric="column_presence", severity=Severity.WARN,
            reference_value="absent", current_value="present", delta=None,
            description=f"New column '{col}' in snapshot B",
            detail="new column",
        ))

    for col in cols_a & cols_b:
        ca, cb = profile_a["columns"][col], profile_b["columns"][col]

        if ca["dtype"] != cb["dtype"]:
            findings.append(DriftFinding(
                column=col, metric="dtype", severity=Severity.CRITICAL,
                reference_value=ca["dtype"], current_value=cb["dtype"], delta=None,
                description=f"'{col}' dtype changed {ca['dtype']} -> {cb['dtype']}",
                detail=f"{ca['dtype']} -> {cb['dtype']}",
            ))

        null_delta = cb["null_pct"] - ca["null_pct"]
        sev = _null_severity(null_delta)
        if sev != Severity.OK:
            findings.append(DriftFinding(
                column=col, metric="null_pct", severity=sev,
                reference_value=round(ca["null_pct"], 4),
                current_value=round(cb["null_pct"], 4),
                delta=round(null_delta, 4),
                description=f"'{col}' null rate changed by {null_delta:+.1%}",
                detail=f"{ca['null_pct']:.1%} -> {cb['null_pct']:.1%}  ({null_delta:+.1%})",
            ))

        if ca["col_type"] == "numeric" and ca.get("stats") and cb.get("stats"):
            mean_a, mean_b = ca["stats"]["mean"], cb["stats"]["mean"]
            std_a = ca["stats"]["std"] or 0.0
            delta_mean = mean_b - mean_a
            sev = _mean_shift_severity(delta_mean, std_a)
            if sev != Severity.OK:
                findings.append(DriftFinding(
                    column=col, metric="mean_shift", severity=sev,
                    reference_value=round(mean_a, 4), current_value=round(mean_b, 4),
                    delta=round(delta_mean, 4),
                    description=f"'{col}' mean shifted by {delta_mean:+.3g}",
                    detail=f"mean {mean_a:.3g} -> {mean_b:.3g}  ({delta_mean:+.3g})",
                ))

        elif ca["col_type"] == "categorical" and ca.get("top_values") and cb.get("top_values"):
            js = _js_divergence_from_dicts(ca["top_values"], cb["top_values"])
            sev = _js_severity(js)
            if sev != Severity.OK:
                findings.append(DriftFinding(
                    column=col, metric="js_divergence", severity=sev,
                    reference_value=None, current_value=None, delta=round(js, 4),
                    description=f"'{col}' categorical distribution drifted (JS={js:.3f})",
                    detail=f"JS={js:.3f}",
                ))

    findings.sort(key=lambda f: _SEVERITY_ORDER[f.severity])
    return findings


def compute_drift_score(findings: list[DriftFinding]) -> int:
    """Return a 0-100 data health score. 100 = no drift, 0 = severely degraded."""
    penalty = sum(20 if f.severity == Severity.CRITICAL else 5 for f in findings)
    return max(0, 100 - penalty)


def detect_drift(
    ref_profile: dict,
    current_df: pd.DataFrame,
    skip_columns: set[str] | None = None,
    psi_warn: float = 0.1,
    psi_crit: float = 0.25,
    js_warn: float = 0.1,
    js_crit: float = 0.3,
    null_warn: float = 0.05,
    null_crit: float = 0.15,
) -> list[DriftFinding]:
    skip = skip_columns or set()
    findings: list[DriftFinding] = []
    ref_cols = set(ref_profile["columns"].keys()) - skip
    cur_cols = set(current_df.columns) - skip

    for col in ref_cols - cur_cols:
        findings.append(DriftFinding(
            column=col, metric="column_presence", severity=Severity.CRITICAL,
            reference_value="present", current_value="missing", delta=None,
            description=f"Column '{col}' is missing from current data",
            detail="present -> missing",
        ))

    for col in cur_cols - ref_cols:
        findings.append(DriftFinding(
            column=col, metric="column_presence", severity=Severity.WARN,
            reference_value="absent", current_value="present", delta=None,
            description=f"New column '{col}' appeared in current data",
            detail="new column",
        ))

    for col in ref_cols & cur_cols:
        ref_col = ref_profile["columns"][col]
        series = current_df[col]

        cur_dtype = str(series.dtype)
        dtype_changed = cur_dtype != ref_col["dtype"]
        if dtype_changed:
            findings.append(DriftFinding(
                column=col, metric="dtype", severity=Severity.CRITICAL,
                reference_value=ref_col["dtype"], current_value=cur_dtype, delta=None,
                description=f"'{col}' dtype changed {ref_col['dtype']} -> {cur_dtype}",
                detail=f"{ref_col['dtype']} -> {cur_dtype}",
            ))

        cur_null = float(series.isna().mean())
        null_delta = cur_null - ref_col["null_pct"]
        sev = _null_severity(null_delta, null_warn, null_crit)
        if sev != Severity.OK:
            findings.append(DriftFinding(
                column=col, metric="null_pct", severity=sev,
                reference_value=round(ref_col["null_pct"], 4),
                current_value=round(cur_null, 4),
                delta=round(null_delta, 4),
                description=f"'{col}' null rate changed by {null_delta:+.1%}",
                detail=f"{ref_col['null_pct']:.1%} -> {cur_null:.1%}  ({null_delta:+.1%})",
            ))

        # Skip distribution checks when dtype changed — finding already reported above.
        if not dtype_changed:
            if ref_col["col_type"] == "numeric" and ref_col.get("bin_edges") is not None:
                psi = compute_psi(ref_col["bin_edges"], ref_col["bin_proportions"], series)
                if psi is not None:
                    sev = _psi_severity(psi, psi_warn, psi_crit)
                    if sev != Severity.OK:
                        ref_mean = ref_col.get("stats", {}).get("mean")
                        non_null = series.dropna()
                        cur_mean = float(non_null.mean()) if len(non_null) > 0 else None
                        if ref_mean is not None and cur_mean is not None:
                            detail = f"mean {ref_mean:.3g} -> {cur_mean:.3g}  (PSI={psi:.3f})"
                        else:
                            detail = f"PSI={psi:.3f}"
                        findings.append(DriftFinding(
                            column=col, metric="psi", severity=sev,
                            reference_value=None, current_value=None,
                            delta=round(psi, 4),
                            description=f"'{col}' numeric distribution drifted (PSI={psi:.3f})",
                            detail=detail,
                        ))

            elif ref_col["col_type"] == "categorical" and ref_col.get("top_values"):
                js = compute_js_divergence(ref_col["top_values"], series)
                sev = _js_severity(js, js_warn, js_crit)
                if sev != Severity.OK:
                    findings.append(DriftFinding(
                        column=col, metric="js_divergence", severity=sev,
                        reference_value=None, current_value=None,
                        delta=round(js, 4),
                        description=f"'{col}' categorical distribution drifted (JS={js:.3f})",
                        detail=f"JS={js:.3f}",
                    ))

    findings.sort(key=lambda f: _SEVERITY_ORDER[f.severity])
    return findings
