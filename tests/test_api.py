from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from drift_doctor import DriftResult, check_drift, diff_snapshots, snapshot
from drift_doctor.detector import Severity


@pytest.fixture()
def ref_csv(tmp_path):
    df = pd.DataFrame({
        "age": [25, 30, 35, 40, 45],
        "status": ["active", "active", "inactive", "active", "churned"],
    })
    p = tmp_path / "ref.csv"
    df.to_csv(p, index=False)
    return p


@pytest.fixture()
def ref_snapshot(ref_csv):
    return snapshot(ref_csv)


def test_snapshot_returns_profile(ref_snapshot):
    assert "columns" in ref_snapshot
    assert "age" in ref_snapshot["columns"]
    assert ref_snapshot["row_count"] == 5


def test_snapshot_writes_file(ref_csv):
    snapshot(ref_csv)
    snap_dir = ref_csv.parent / ".driftdoctor"
    assert (snap_dir / "ref_latest.json").exists()


def test_check_drift_no_drift(ref_csv, ref_snapshot):
    result = check_drift(ref_csv)
    assert isinstance(result, DriftResult)
    assert not result.has_drift
    assert result.summary["total"] == 0


def test_check_drift_detects_null_spike(ref_csv, ref_snapshot, tmp_path):
    drifted = pd.DataFrame({
        "age": [None, None, None, 40, 45],
        "status": ["active", "active", "inactive", "active", "churned"],
    })
    cur = tmp_path / "cur.csv"
    drifted.to_csv(cur, index=False)

    snap_path = ref_csv.parent / ".driftdoctor" / "ref_latest.json"
    result = check_drift(cur, ref=snap_path)
    assert result.has_drift
    cols = [f.column for f in result.critical]
    assert "age" in cols


def test_check_drift_missing_column(ref_csv, ref_snapshot, tmp_path):
    cur_df = pd.DataFrame({"status": ["active", "active", "inactive", "active", "churned"]})
    cur = tmp_path / "cur.csv"
    cur_df.to_csv(cur, index=False)

    snap_path = ref_csv.parent / ".driftdoctor" / "ref_latest.json"
    result = check_drift(cur, ref=snap_path)
    assert any(f.metric == "column_presence" and f.severity == Severity.CRITICAL
               for f in result.findings)


def test_result_raise_on_critical(ref_csv, ref_snapshot, tmp_path):
    cur_df = pd.DataFrame({"status": ["active"] * 5})
    cur = tmp_path / "cur.csv"
    cur_df.to_csv(cur, index=False)

    snap_path = ref_csv.parent / ".driftdoctor" / "ref_latest.json"
    result = check_drift(cur, ref=snap_path)
    with pytest.raises(RuntimeError, match="Critical drift"):
        result.raise_on_critical()


def test_check_drift_skip(ref_csv, ref_snapshot, tmp_path):
    cur_df = pd.DataFrame({"status": ["active"] * 5})
    cur = tmp_path / "cur.csv"
    cur_df.to_csv(cur, index=False)

    snap_path = ref_csv.parent / ".driftdoctor" / "ref_latest.json"
    result = check_drift(cur, ref=snap_path, skip=["age"])
    assert all(f.column != "age" for f in result.findings)


def test_diff_snapshots(ref_csv, ref_snapshot, tmp_path):
    drifted = pd.DataFrame({
        "age": [50, 55, 60, 65, 70],
        "status": ["churned"] * 5,
    })
    cur = tmp_path / "cur.csv"
    drifted.to_csv(cur, index=False)
    snapshot(cur)

    snap_a = ref_csv.parent / ".driftdoctor" / "ref_latest.json"
    snap_b = tmp_path / ".driftdoctor" / "cur_latest.json"
    result = diff_snapshots(snap_a, snap_b)
    assert isinstance(result, DriftResult)
    assert result.has_drift
