from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from drift_doctor.cli import app

runner = CliRunner()


@pytest.fixture()
def snap_and_csv(tmp_path):
    """Snapshot of 'age' only, then a drifted CSV."""
    import json as _json
    from drift_doctor.profiler import profile_dataframe
    from drift_doctor.snapshot import SNAPSHOT_DIR

    ref_df = pd.DataFrame({"age": [25, 30, 35, 40, 45]})
    profile = profile_dataframe(ref_df)
    snap_dir = tmp_path / SNAPSHOT_DIR
    snap_dir.mkdir()
    snap_path = snap_dir / "current_latest.json"
    snap_path.write_text(_json.dumps({"created_at": "2026-01-01T00:00:00Z", "profile": profile}), encoding="utf-8")

    # Drifted CSV — age mean shifted from 35 to 80 (critical PSI)
    cur_df = pd.DataFrame({"age": [75, 78, 80, 82, 85]})
    csv_path = tmp_path / "current.csv"
    cur_df.to_csv(csv_path, index=False)
    return csv_path, snap_path


@pytest.fixture()
def warn_only_snap_and_csv(tmp_path):
    """Snapshot + CSV that produces only WARN findings (small null shift)."""
    import json as _json
    from drift_doctor.profiler import profile_dataframe
    from drift_doctor.snapshot import SNAPSHOT_DIR

    ref_df = pd.DataFrame({"age": [25, 30, 35, 40, 45]})
    profile = profile_dataframe(ref_df)
    snap_dir = tmp_path / SNAPSHOT_DIR
    snap_dir.mkdir()
    snap_path = snap_dir / "current_latest.json"
    snap_path.write_text(_json.dumps({"created_at": "2026-01-01T00:00:00Z", "profile": profile}), encoding="utf-8")

    # Only 2 nulls out of 10 — triggers null warn (~20% > 5% threshold)
    cur_df = pd.DataFrame({"age": [25, 30, None, 40, 45, 25, 30, None, 40, 45]})
    csv_path = tmp_path / "current.csv"
    cur_df.to_csv(csv_path, index=False)
    return csv_path, snap_path


class TestFailOn:
    def test_default_fail_on_critical_exits_1_on_critical(self, snap_and_csv):
        csv_path, snap_path = snap_and_csv
        result = runner.invoke(app, ["check", str(csv_path), "--ref", str(snap_path)])
        assert result.exit_code == 1

    def test_explicit_fail_on_critical_exits_1_on_critical(self, snap_and_csv):
        csv_path, snap_path = snap_and_csv
        result = runner.invoke(app, ["check", str(csv_path), "--ref", str(snap_path), "--fail-on", "critical"])
        assert result.exit_code == 1

    def test_fail_on_any_exits_1_on_warn(self, snap_and_csv, monkeypatch):
        """--fail-on any: exit 1 even when only WARN findings."""
        from drift_doctor import cli as cli_mod
        from drift_doctor.detector import DriftFinding, Severity
        warn_finding = DriftFinding(
            column="age", metric="null_pct", severity=Severity.WARN,
            reference_value=0.0, current_value=0.1, delta=0.1,
            description="null rate increased", detail="0.0% -> 10.0%",
        )
        monkeypatch.setattr(cli_mod, "detect_drift", lambda *a, **kw: [warn_finding])
        csv_path, snap_path = snap_and_csv
        result = runner.invoke(app, [
            "check", str(csv_path), "--ref", str(snap_path), "--fail-on", "any",
        ])
        assert result.exit_code == 1

    def test_fail_on_critical_exits_0_on_warn_only(self, snap_and_csv, monkeypatch):
        """--fail-on critical: exit 0 when only WARN findings exist."""
        from drift_doctor import cli as cli_mod
        from drift_doctor.detector import DriftFinding, Severity
        warn_finding = DriftFinding(
            column="age", metric="null_pct", severity=Severity.WARN,
            reference_value=0.0, current_value=0.1, delta=0.1,
            description="null rate increased", detail="0.0% -> 10.0%",
        )
        monkeypatch.setattr(cli_mod, "detect_drift", lambda *a, **kw: [warn_finding])
        csv_path, snap_path = snap_and_csv
        result = runner.invoke(app, [
            "check", str(csv_path), "--ref", str(snap_path), "--fail-on", "critical",
        ])
        assert result.exit_code == 0

    def test_exits_0_when_no_findings(self, tmp_path):
        import json as _json
        from drift_doctor.profiler import profile_dataframe
        from drift_doctor.snapshot import SNAPSHOT_DIR

        df = pd.DataFrame({"age": [25, 30, 35, 40, 45]})
        profile = profile_dataframe(df)
        snap_dir = tmp_path / SNAPSHOT_DIR
        snap_dir.mkdir()
        snap_path = snap_dir / "current_latest.json"
        snap_path.write_text(_json.dumps({"created_at": "2026-01-01T00:00:00Z", "profile": profile}), encoding="utf-8")
        csv_path = tmp_path / "current.csv"
        df.to_csv(csv_path, index=False)

        result = runner.invoke(app, ["check", str(csv_path), "--ref", str(snap_path)])
        assert result.exit_code == 0


class TestVersion:
    def test_version_flag_exits_0(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0

    def test_version_flag_shows_version(self):
        from drift_doctor import __version__
        result = runner.invoke(app, ["--version"])
        assert __version__ in result.output

    def test_short_version_flag(self):
        result = runner.invoke(app, ["-V"])
        assert result.exit_code == 0


class TestSince:
    def test_since_finds_closest_snapshot(self, tmp_path, monkeypatch):
        import json as _json
        from datetime import datetime, timedelta, timezone
        from drift_doctor.profiler import profile_dataframe
        from drift_doctor.snapshot import SNAPSHOT_DIR

        monkeypatch.chdir(tmp_path)

        df = pd.DataFrame({"age": [25, 30, 35, 40, 45]})
        profile = profile_dataframe(df)
        snap_dir = tmp_path / SNAPSHOT_DIR
        snap_dir.mkdir()

        now = datetime.now(timezone.utc)
        ts_old = (now - timedelta(days=7)).strftime("%Y%m%dT%H%M%SZ")
        (snap_dir / f"mydata_{ts_old}.json").write_text(
            _json.dumps({"created_at": ts_old, "profile": profile}), encoding="utf-8"
        )
        ts_new = now.strftime("%Y%m%dT%H%M%SZ")
        (snap_dir / f"mydata_{ts_new}.json").write_text(
            _json.dumps({"created_at": ts_new, "profile": profile}), encoding="utf-8"
        )
        (snap_dir / "mydata_latest.json").write_text(
            _json.dumps({"created_at": ts_new, "profile": profile}), encoding="utf-8"
        )

        csv_path = tmp_path / "mydata.csv"
        df.to_csv(csv_path, index=False)

        result = runner.invoke(app, ["check", str(csv_path), "--since", "7d"])
        assert result.exit_code == 0

    def test_since_invalid_duration_exits_nonzero(self, tmp_path):
        csv_path = tmp_path / "mydata.csv"
        pd.DataFrame({"x": [1]}).to_csv(csv_path, index=False)
        result = runner.invoke(app, ["check", str(csv_path), "--since", "bad"])
        assert result.exit_code != 0


class TestQuiet:
    def test_quiet_suppresses_output(self, snap_and_csv, monkeypatch):
        from drift_doctor import cli as cli_mod
        from drift_doctor.detector import DriftFinding, Severity
        crit_finding = DriftFinding(
            column="age", metric="psi", severity=Severity.CRITICAL,
            reference_value=35.0, current_value=80.0, delta=45.0,
            description="PSI critical", detail="PSI=3.0",
        )
        monkeypatch.setattr(cli_mod, "detect_drift", lambda *a, **kw: [crit_finding])
        csv_path, snap_path = snap_and_csv
        result = runner.invoke(app, ["check", str(csv_path), "--ref", str(snap_path), "--quiet"])
        assert result.exit_code == 1
        assert result.output.strip() == ""

    def test_quiet_still_writes_output_file(self, snap_and_csv, tmp_path, monkeypatch):
        from drift_doctor import cli as cli_mod
        from drift_doctor.detector import DriftFinding, Severity
        crit_finding = DriftFinding(
            column="age", metric="psi", severity=Severity.CRITICAL,
            reference_value=35.0, current_value=80.0, delta=45.0,
            description="PSI critical", detail="PSI=3.0",
        )
        monkeypatch.setattr(cli_mod, "detect_drift", lambda *a, **kw: [crit_finding])
        csv_path, snap_path = snap_and_csv
        out = tmp_path / "report.json"
        result = runner.invoke(app, [
            "check", str(csv_path), "--ref", str(snap_path),
            "--quiet", "--output-file", str(out),
        ])
        assert result.exit_code == 1
        assert result.output.strip() == ""
        assert out.exists()


class TestSnapshots:
    def test_snapshots_lists_files(self, snap_and_csv, monkeypatch):
        import json as _json
        csv_path, snap_path = snap_and_csv
        tmp_path = snap_path.parent.parent
        monkeypatch.chdir(tmp_path)
        # snapshots command requires versioned files (not _latest); add one
        versioned = snap_path.parent / "current_20260101T120000Z.json"
        versioned.write_text(snap_path.read_text(encoding="utf-8"), encoding="utf-8")
        result = runner.invoke(app, ["snapshots", str(csv_path)])
        assert result.exit_code == 0
        assert "current" in result.output

    def test_snapshots_no_snapshot_exits_1(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        csv_path = tmp_path / "ghost.csv"
        pd.DataFrame({"x": [1]}).to_csv(csv_path, index=False)
        result = runner.invoke(app, ["snapshots", str(csv_path)])
        assert result.exit_code == 1
        assert "drift-doctor snapshot" in result.output


class TestOnboarding:
    def test_no_snapshot_shows_hint(self, tmp_path):
        """When no snapshot exists, output should contain the snapshot command hint."""
        csv_path = tmp_path / "mydata.csv"
        pd.DataFrame({"x": [1, 2, 3]}).to_csv(csv_path, index=False)
        result = runner.invoke(app, ["check", str(csv_path)])
        assert result.exit_code == 1
        assert "drift-doctor snapshot" in result.output

    def test_no_snapshot_mentions_filename(self, tmp_path):
        csv_path = tmp_path / "customers.csv"
        pd.DataFrame({"x": [1, 2, 3]}).to_csv(csv_path, index=False)
        result = runner.invoke(app, ["check", str(csv_path)])
        assert "customers" in result.output


class TestModelUpgrade:
    def test_diagnose_uses_new_model(self, monkeypatch):
        import drift_doctor.diagnose as diag_mod
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        captured = {}

        class FakeMessages:
            def create(self, **kwargs):
                captured["model"] = kwargs.get("model")
                class FakeMsg:
                    content = [type("C", (), {"text": "diagnosis"})()]
                return FakeMsg()

        class FakeClient:
            messages = FakeMessages()

        monkeypatch.setattr(diag_mod.anthropic, "Anthropic", lambda **kw: FakeClient())
        from drift_doctor.detector import DriftFinding, Severity
        findings = [DriftFinding(
            column="age", metric="psi", severity=Severity.CRITICAL,
            reference_value=35.0, current_value=80.0, delta=45.0,
            description="mean shifted", detail="mean 35 -> 80",
        )]
        diag_mod.run_diagnosis(findings, {"row_count": 5, "columns": {}}, 5, [])
        assert captured.get("model") == "claude-sonnet-4-6"
