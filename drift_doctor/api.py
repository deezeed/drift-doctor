from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .detector import DriftFinding, Severity, compute_drift_score, detect_drift, diff_profiles
from .profiler import profile_dataframe
from .snapshot import load_latest_snapshot, save_snapshot


def _load(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(p)
    if suffix in (".parquet", ".pq"):
        return pd.read_parquet(p)
    raise ValueError(f"Unsupported format '{suffix}'. Use .csv or .parquet")


def _load_snap(path: str | Path) -> dict:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8"))


@dataclass
class DriftResult:
    """Return type for check_drift and diff_snapshots."""

    findings: list[DriftFinding]
    ref_row_count: int
    cur_row_count: int
    snapshot_date: str = ""

    @property
    def critical(self) -> list[DriftFinding]:
        return [f for f in self.findings if f.severity == Severity.CRITICAL]

    @property
    def warnings(self) -> list[DriftFinding]:
        return [f for f in self.findings if f.severity == Severity.WARN]

    @property
    def score(self) -> int:
        """Data health score 0-100. 100 = no drift, each critical -20, each warn -5."""
        return compute_drift_score(self.findings)

    @property
    def has_drift(self) -> bool:
        return bool(self.findings)

    @property
    def summary(self) -> dict:
        return {
            "critical": len(self.critical),
            "warn": len(self.warnings),
            "total": len(self.findings),
        }

    def raise_on_critical(self) -> None:
        """Raise RuntimeError if any critical findings exist."""
        if self.critical:
            cols = ", ".join(f.column for f in self.critical)
            raise RuntimeError(
                f"Critical drift detected in {len(self.critical)} column(s): {cols}"
            )

    def to_html(self, source: str = "") -> str:
        """Return a complete HTML report string."""
        from .reporter_html import render_html
        return render_html(self, source=source)

    def notify(self, webhook_url: str, source: str = "") -> None:
        """Send findings to a Slack or generic webhook URL.

        No-op when there are no findings. Slack webhooks
        (hooks.slack.com) receive a Block Kit payload; all other URLs
        receive a plain JSON report.
        """
        from .notifier import notify as _notify
        _notify(self, webhook_url, source=source)


def snapshot(path: str | Path) -> dict:
    """Profile a dataset and save a reference snapshot to .driftdoctor/.

    Returns the profile dict (also persisted to disk).
    """
    p = Path(path)
    df = _load(p)
    profile = profile_dataframe(df)
    save_snapshot(profile, str(p), base_dir=p.parent)
    return profile


def check_drift(
    path: str | Path,
    ref: str | Path | None = None,
    skip: list[str] | None = None,
    psi_warn: float = 0.1,
    psi_crit: float = 0.25,
    js_warn: float = 0.1,
    js_crit: float = 0.3,
    null_warn: float = 0.05,
    null_crit: float = 0.15,
) -> DriftResult:
    """Check a dataset for drift against its latest snapshot.

    Parameters
    ----------
    path:
        Path to the current dataset (CSV or Parquet).
    ref:
        Path to a specific snapshot JSON. If omitted, uses the latest
        snapshot saved for *path* via :func:`snapshot`.
    skip:
        Column names to exclude from all checks.
    psi_warn / psi_crit:
        PSI warn / critical thresholds (numeric columns).
    js_warn / js_crit:
        JS-divergence warn / critical thresholds (categorical columns).
    null_warn / null_crit:
        Null-rate delta warn / critical thresholds.
    """
    p = Path(path)
    if ref is not None:
        snap = _load_snap(ref)
    else:
        snap = load_latest_snapshot(str(p), base_dir=p.parent)

    df = _load(p)
    findings = detect_drift(
        snap["profile"], df,
        skip_columns=set(skip or []),
        psi_warn=psi_warn, psi_crit=psi_crit,
        js_warn=js_warn, js_crit=js_crit,
        null_warn=null_warn, null_crit=null_crit,
    )
    return DriftResult(
        findings=findings,
        ref_row_count=snap["profile"]["row_count"],
        cur_row_count=len(df),
        snapshot_date=snap.get("created_at", ""),
    )


def diff_snapshots(
    snapshot_a: str | Path,
    snapshot_b: str | Path,
    skip: list[str] | None = None,
) -> DriftResult:
    """Compare two snapshot files directly — no raw data needed."""
    snap_a = _load_snap(snapshot_a)
    snap_b = _load_snap(snapshot_b)
    findings = diff_profiles(
        snap_a["profile"], snap_b["profile"],
        skip_columns=set(skip or []),
    )
    return DriftResult(
        findings=findings,
        ref_row_count=snap_a["profile"]["row_count"],
        cur_row_count=snap_b["profile"]["row_count"],
        snapshot_date=snap_b.get("created_at", ""),
    )
