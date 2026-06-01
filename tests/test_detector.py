import numpy as np
import pandas as pd
import pytest

from drift_doctor.detector import (
    DriftFinding,
    Severity,
    compute_js_divergence,
    compute_psi,
    detect_drift,
)
from drift_doctor.profiler import profile_dataframe


# ── PSI ─────────────────────────────────────────────────────────────────────

def test_psi_identical_distribution():
    data = list(range(100))
    ref_profile = profile_dataframe(pd.DataFrame({"x": data}))
    col = ref_profile["columns"]["x"]
    psi = compute_psi(col["bin_edges"], col["bin_proportions"], pd.Series(data))
    assert psi is not None
    assert psi < 0.02


def test_psi_large_shift_is_critical():
    rng = np.random.default_rng(42)
    ref = profile_dataframe(pd.DataFrame({"x": rng.normal(0, 1, 1000)}))
    col = ref["columns"]["x"]
    psi = compute_psi(col["bin_edges"], col["bin_proportions"], pd.Series(rng.normal(10, 1, 1000)))
    assert psi is not None
    assert psi >= 0.25


def test_psi_no_change_in_normal_distribution():
    rng = np.random.default_rng(7)
    ref = profile_dataframe(pd.DataFrame({"x": rng.normal(0, 1, 2000)}))
    col = ref["columns"]["x"]
    psi = compute_psi(col["bin_edges"], col["bin_proportions"], pd.Series(rng.normal(0, 1, 2000)))
    assert psi is not None
    assert psi < 0.1


def test_psi_none_when_all_null():
    rng = np.random.default_rng(0)
    ref = profile_dataframe(pd.DataFrame({"x": rng.normal(0, 1, 100)}))
    col = ref["columns"]["x"]
    psi = compute_psi(col["bin_edges"], col["bin_proportions"], pd.Series([None] * 50, dtype=float))
    assert psi is None


def test_psi_handles_out_of_range_values():
    ref = profile_dataframe(pd.DataFrame({"x": [1.0, 2.0, 3.0, 4.0, 5.0] * 20}))
    col = ref["columns"]["x"]
    # Current data has extreme outliers beyond the reference range
    current = pd.Series([100.0, 200.0, -100.0] * 10)
    psi = compute_psi(col["bin_edges"], col["bin_proportions"], current)
    assert psi is not None
    assert psi >= 0.25  # should flag this as critical


# ── JS Divergence ────────────────────────────────────────────────────────────

def test_js_identical():
    ref = {"cat_a": 0.5, "cat_b": 0.3, "cat_c": 0.2}
    current = pd.Series(["cat_a"] * 50 + ["cat_b"] * 30 + ["cat_c"] * 20)
    assert compute_js_divergence(ref, current) < 0.05


def test_js_completely_different():
    ref = {"cat_a": 1.0}
    current = pd.Series(["cat_b"] * 100)
    assert compute_js_divergence(ref, current) > 0.3


def test_js_new_category_raises_divergence():
    ref = {"cat_a": 0.7, "cat_b": 0.3}
    current = pd.Series(["cat_a"] * 50 + ["cat_b"] * 20 + ["new_cat"] * 30)
    js = compute_js_divergence(ref, current)
    assert js > 0.05


def test_js_bounded_0_to_1():
    ref = {"x": 0.5, "y": 0.5}
    current = pd.Series(["z"] * 100)
    js = compute_js_divergence(ref, current)
    assert 0.0 <= js <= 1.0


# ── detect_drift full pipeline ───────────────────────────────────────────────

def test_missing_column_is_critical():
    ref = profile_dataframe(pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]}))
    findings = detect_drift(ref, pd.DataFrame({"a": [1, 2, 3]}))
    f = next(x for x in findings if x.column == "b" and x.metric == "column_presence")
    assert f.severity == Severity.CRITICAL


def test_new_column_is_warn():
    ref = profile_dataframe(pd.DataFrame({"a": [1, 2, 3]}))
    findings = detect_drift(ref, pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]}))
    f = next(x for x in findings if x.column == "b" and x.metric == "column_presence")
    assert f.severity == Severity.WARN


def test_dtype_change_is_critical():
    ref = profile_dataframe(pd.DataFrame({"a": [1, 2, 3]}))
    findings = detect_drift(ref, pd.DataFrame({"a": ["1", "2", "3"]}))
    f = next(x for x in findings if x.metric == "dtype")
    assert f.severity == Severity.CRITICAL


def test_large_null_increase_is_critical():
    ref = profile_dataframe(pd.DataFrame({"a": [1.0] * 20}))
    current = pd.DataFrame({"a": [1.0] * 10 + [None] * 10})
    findings = detect_drift(ref, current)
    f = next(x for x in findings if x.metric == "null_pct")
    assert f.severity == Severity.CRITICAL
    assert f.delta == pytest.approx(0.5)


def test_small_null_change_no_finding():
    ref = profile_dataframe(pd.DataFrame({"a": [1.0] * 100}))
    # Only 2% nulls — below 5% threshold
    current = pd.DataFrame({"a": [1.0] * 98 + [None] * 2})
    findings = detect_drift(ref, current)
    null_findings = [x for x in findings if x.metric == "null_pct"]
    assert len(null_findings) == 0


def test_no_drift_for_same_data():
    rng = np.random.default_rng(99)
    data = rng.normal(0, 1, 500).tolist()
    df = pd.DataFrame({"v": data})
    ref = profile_dataframe(df)
    findings = detect_drift(ref, df)
    assert all(f.severity == Severity.OK for f in findings) or len(findings) == 0


def test_numeric_distribution_drift_detected():
    rng = np.random.default_rng(42)
    ref = profile_dataframe(pd.DataFrame({"v": rng.normal(0, 1, 1000)}))
    current = pd.DataFrame({"v": rng.normal(10, 1, 1000)})
    findings = detect_drift(ref, current)
    psi_findings = [f for f in findings if f.metric == "psi"]
    assert len(psi_findings) == 1
    assert psi_findings[0].severity == Severity.CRITICAL


def test_categorical_distribution_drift_detected():
    ref = profile_dataframe(pd.DataFrame({"cat": ["a"] * 90 + ["b"] * 10}))
    current = pd.DataFrame({"cat": ["a"] * 10 + ["b"] * 90})
    findings = detect_drift(ref, current)
    js_findings = [f for f in findings if f.metric == "js_divergence"]
    assert len(js_findings) == 1
    assert js_findings[0].severity == Severity.CRITICAL


def test_findings_sorted_critical_first():
    rng = np.random.default_rng(0)
    ref = profile_dataframe(pd.DataFrame({
        "num": rng.normal(0, 1, 500),
        "cat": ["a"] * 400 + ["b"] * 100,
    }))
    current = pd.DataFrame({
        "num": rng.normal(10, 1, 500),
        "cat": ["c"] * 500,
    })
    findings = detect_drift(ref, current)
    order = {Severity.CRITICAL: 0, Severity.WARN: 1, Severity.OK: 2}
    severities = [order[f.severity] for f in findings]
    assert severities == sorted(severities)
