from __future__ import annotations

import json
import sys
from enum import Enum
from pathlib import Path

import pandas as pd
import typer
from rich.console import Console


class OutputFormat(str, Enum):
    table = "table"
    json = "json"


class FailOn(str, Enum):
    critical = "critical"
    any = "any"

from .detector import detect_drift, diff_profiles
from .profiler import profile_dataframe
from .reporter import console as rich_console
from .reporter import render_drift_report, render_snapshot_summary
from .snapshot import NoSnapshotError, load_latest_snapshot, save_snapshot

app = typer.Typer(
    name="drift-doctor",
    help="Monitor datasets for schema and distribution drift.",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
)
err = Console(stderr=True, style="bold red", legacy_windows=False)


def _no_snapshot_exit(source_path: str) -> None:
    name = Path(source_path).name
    rich_console.print(f"\n[red]No snapshot found for[/red] [bold]{name}[/bold]")
    rich_console.print(f"  [dim]Create one first:[/dim] [bold cyan]drift-doctor snapshot {source_path}[/bold cyan]\n")
    raise typer.Exit(1)


def _load_snapshot(data_path: str, ref_override: str) -> dict:
    if ref_override:
        p = Path(ref_override)
        if not p.exists():
            raise FileNotFoundError(f"Snapshot not found: {ref_override}")
        return json.loads(p.read_text(encoding="utf-8"))
    return load_latest_snapshot(data_path)


def _load(path: str) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        err.print(f"File not found: {path}")
        raise typer.Exit(1)
    suffix = p.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(p)
    if suffix in (".parquet", ".pq"):
        return pd.read_parquet(p)
    err.print(f"Unsupported format '{suffix}'. Use .csv or .parquet")
    raise typer.Exit(1)


def _parse_skip(skip_str: str) -> set[str]:
    return {c.strip() for c in skip_str.split(",") if c.strip()}


@app.command()
def snapshot(
    path: str = typer.Argument(..., help="Path to reference dataset (CSV or Parquet)"),
) -> None:
    """Profile a dataset and save a reference snapshot to .driftdoctor/."""
    df = _load(path)
    profile = profile_dataframe(df)
    saved = save_snapshot(profile, path)
    render_snapshot_summary(profile, path)
    rich_console.print(f"[dim]Snapshot written: {saved}[/dim]\n")


@app.command()
def check(
    path: str = typer.Argument(..., help="Path to current dataset to check for drift"),
    ref: str = typer.Option("", "--ref", "-r", help="Path to a specific snapshot JSON"),
    skip: str = typer.Option("", "--skip", "-s", help="Comma-separated columns to exclude (e.g. id,created_at)"),
    format: OutputFormat = typer.Option(OutputFormat.table, "--format", "-f", help="Output format: table or json"),
    output_file: str = typer.Option("", "--output-file", "-o", help="Write JSON report to this file (implies --format json)"),
    psi_warn: float = typer.Option(0.1, "--psi-warn", help="PSI warn threshold"),
    psi_crit: float = typer.Option(0.25, "--psi-crit", help="PSI critical threshold"),
    js_warn: float = typer.Option(0.1, "--js-warn", help="JS-divergence warn threshold"),
    js_crit: float = typer.Option(0.3, "--js-crit", help="JS-divergence critical threshold"),
    null_warn: float = typer.Option(0.05, "--null-warn", help="Null-rate delta warn threshold"),
    null_crit: float = typer.Option(0.15, "--null-crit", help="Null-rate delta critical threshold"),
    notify: str = typer.Option("", "--notify", "-n", help="Webhook URL to POST findings (Slack or generic)"),
    fail_on: FailOn = typer.Option(FailOn.critical, "--fail-on", help="Exit 1 on: 'critical' (default) or 'any' findings"),
) -> None:
    """Compare current dataset against the latest snapshot and report drift."""
    try:
        snap = _load_snapshot(path, ref)
    except NoSnapshotError:
        _no_snapshot_exit(path)
    except FileNotFoundError as exc:
        err.print(str(exc))
        raise typer.Exit(1)

    df = _load(path)
    findings = detect_drift(
        snap["profile"], df,
        skip_columns=_parse_skip(skip),
        psi_warn=psi_warn, psi_crit=psi_crit,
        js_warn=js_warn, js_crit=js_crit,
        null_warn=null_warn, null_crit=null_crit,
    )

    use_html = output_file and Path(output_file).suffix.lower() == ".html"
    use_json = not use_html and (format == OutputFormat.json or bool(output_file))

    if use_html:
        from .api import DriftResult
        result = DriftResult(
            findings=findings,
            ref_row_count=snap["profile"]["row_count"],
            cur_row_count=len(df),
            snapshot_date=snap.get("created_at", ""),
        )
        Path(output_file).write_text(result.to_html(source=path), encoding="utf-8")
        rich_console.print(f"[dim]Report written: {output_file}[/dim]")
        render_drift_report(findings, snap["profile"]["row_count"], len(df),
                            snapshot_date=snap.get("created_at", ""))
    elif use_json:
        ref_rows = snap["profile"]["row_count"]
        cur_rows = len(df)
        report = {
            "snapshot_date": snap.get("created_at", ""),
            "row_count": {"reference": ref_rows, "current": cur_rows, "delta": cur_rows - ref_rows},
            "summary": {
                "critical": sum(1 for f in findings if f.severity.value == "critical"),
                "warn": sum(1 for f in findings if f.severity.value == "warn"),
                "total": len(findings),
            },
            "findings": [
                {"column": f.column, "metric": f.metric, "severity": f.severity.value,
                 "detail": f.detail or f.description, "delta": f.delta}
                for f in findings
            ],
        }
        report_str = json.dumps(report, indent=2) + "\n"
        if output_file:
            Path(output_file).write_text(report_str, encoding="utf-8")
            rich_console.print(f"[dim]Report written: {output_file}[/dim]")
        else:
            sys.stdout.write(report_str)
    else:
        render_drift_report(
            findings,
            snap["profile"]["row_count"],
            len(df),
            snapshot_date=snap.get("created_at", ""),
        )

    if notify and findings:
        from .notifier import notify as _notify
        from .api import DriftResult
        from .detector import Severity
        result = DriftResult(
            findings=findings,
            ref_row_count=snap["profile"]["row_count"],
            cur_row_count=len(df),
        )
        try:
            _notify(result, notify, source=path)
            rich_console.print(f"[dim]Notification sent to {notify}[/dim]")
        except Exception as exc:
            err.print(f"Notification failed: {exc}")

    if fail_on == FailOn.critical:
        raise typer.Exit(1 if any(f.severity.value == "critical" for f in findings) else 0)
    raise typer.Exit(1 if findings else 0)


@app.command()
def diagnose(
    path: str = typer.Argument(..., help="Path to current dataset to diagnose"),
    ref: str = typer.Option("", "--ref", "-r", help="Path to a specific snapshot JSON"),
    skip: str = typer.Option("", "--skip", "-s", help="Comma-separated columns to exclude"),
    consumers: str = typer.Option("", "--consumers", "-c", help="Comma-separated downstream consumer names"),
    psi_warn: float = typer.Option(0.1, "--psi-warn", help="PSI warn threshold"),
    psi_crit: float = typer.Option(0.25, "--psi-crit", help="PSI critical threshold"),
    js_warn: float = typer.Option(0.1, "--js-warn", help="JS-divergence warn threshold"),
    js_crit: float = typer.Option(0.3, "--js-crit", help="JS-divergence critical threshold"),
    null_warn: float = typer.Option(0.05, "--null-warn", help="Null-rate delta warn threshold"),
    null_crit: float = typer.Option(0.15, "--null-crit", help="Null-rate delta critical threshold"),
    notify: str = typer.Option("", "--notify", "-n", help="Webhook URL to POST findings (Slack or generic)"),
) -> None:
    """Run drift check then get AI-powered root-cause diagnosis via Anthropic API."""
    from .diagnose import run_diagnosis

    try:
        snap = _load_snapshot(path, ref)
    except NoSnapshotError:
        _no_snapshot_exit(path)
    except FileNotFoundError as exc:
        err.print(str(exc))
        raise typer.Exit(1)

    df = _load(path)
    findings = detect_drift(
        snap["profile"], df,
        skip_columns=_parse_skip(skip),
        psi_warn=psi_warn, psi_crit=psi_crit,
        js_warn=js_warn, js_crit=js_crit,
        null_warn=null_warn, null_crit=null_crit,
    )
    render_drift_report(
        findings,
        snap["profile"]["row_count"],
        len(df),
        snapshot_date=snap.get("created_at", ""),
    )

    if not findings:
        rich_console.print("\n[dim]No drift found — skipping AI diagnosis.[/dim]\n")
        return

    if notify:
        from .notifier import notify as _notify
        from .api import DriftResult
        result = DriftResult(findings=findings, ref_row_count=snap["profile"]["row_count"], cur_row_count=len(df))
        try:
            _notify(result, notify, source=path)
            rich_console.print(f"[dim]Notification sent to {notify}[/dim]")
        except Exception as exc:
            err.print(f"Notification failed: {exc}")

    consumer_list = [c.strip() for c in consumers.split(",") if c.strip()]
    run_diagnosis(findings, snap["profile"], len(df), consumer_list)


@app.command()
def diff(
    snapshot_a: str = typer.Argument(..., help="Path to the earlier snapshot JSON"),
    snapshot_b: str = typer.Argument(..., help="Path to the later snapshot JSON"),
    skip: str = typer.Option(
        "", "--skip", "-s",
        help="Comma-separated column names to exclude",
    ),
    format: OutputFormat = typer.Option(
        OutputFormat.table, "--format", "-f",
        help="Output format: table or json",
    ),
    fail_on: FailOn = typer.Option(FailOn.critical, "--fail-on", help="Exit 1 on: 'critical' (default) or 'any' findings"),
) -> None:
    """Compare two snapshots directly — no raw data needed."""
    try:
        snap_a = _load_snapshot(snapshot_a, snapshot_a)
        snap_b = _load_snapshot(snapshot_b, snapshot_b)
    except FileNotFoundError as exc:
        err.print(str(exc))
        raise typer.Exit(1)

    findings = diff_profiles(snap_a["profile"], snap_b["profile"], skip_columns=_parse_skip(skip))

    if format == OutputFormat.json:
        rows_a = snap_a["profile"]["row_count"]
        rows_b = snap_b["profile"]["row_count"]
        output = {
            "snapshot_a": snap_a.get("created_at", snapshot_a),
            "snapshot_b": snap_b.get("created_at", snapshot_b),
            "row_count": {"a": rows_a, "b": rows_b, "delta": rows_b - rows_a},
            "summary": {
                "critical": sum(1 for f in findings if f.severity.value == "critical"),
                "warn": sum(1 for f in findings if f.severity.value == "warn"),
                "total": len(findings),
            },
            "findings": [
                {"column": f.column, "metric": f.metric, "severity": f.severity.value,
                 "detail": f.detail or f.description, "delta": f.delta}
                for f in findings
            ],
        }
        sys.stdout.write(json.dumps(output, indent=2) + "\n")
    else:
        date_a = snap_a.get("created_at", snapshot_a)
        date_b = snap_b.get("created_at", snapshot_b)
        rich_console.print(f"\n[bold]Comparing snapshots:[/bold] [dim]{date_a}[/dim] -> [dim]{date_b}[/dim]")
        render_drift_report(
            findings,
            snap_a["profile"]["row_count"],
            snap_b["profile"]["row_count"],
            snapshot_date="",
        )

    if fail_on == FailOn.critical:
        raise typer.Exit(1 if any(f.severity.value == "critical" for f in findings) else 0)
    raise typer.Exit(1 if findings else 0)


def _parse_interval(s: str) -> int:
    """Parse '30s', '5m', '1h' -> seconds."""
    s = s.strip().lower()
    if s.endswith("h"):
        return int(s[:-1]) * 3600
    if s.endswith("m"):
        return int(s[:-1]) * 60
    if s.endswith("s"):
        return int(s[:-1])
    return int(s)


@app.command()
def watch(
    path: str = typer.Argument(..., help="Path to dataset to monitor"),
    interval: str = typer.Option("1h", "--interval", "-i", help="Check interval: 30s, 5m, 1h"),
    ref: str = typer.Option("", "--ref", "-r", help="Path to a specific snapshot JSON"),
    skip: str = typer.Option("", "--skip", "-s", help="Comma-separated columns to exclude"),
    notify: str = typer.Option("", "--notify", "-n", help="Webhook URL to POST findings"),
    psi_warn: float = typer.Option(0.1, "--psi-warn"),
    psi_crit: float = typer.Option(0.25, "--psi-crit"),
    js_warn: float = typer.Option(0.1, "--js-warn"),
    js_crit: float = typer.Option(0.3, "--js-crit"),
    null_warn: float = typer.Option(0.05, "--null-warn"),
    null_crit: float = typer.Option(0.15, "--null-crit"),
) -> None:
    """Repeatedly check a dataset for drift at a fixed interval. Press Ctrl+C to stop."""
    import time
    from datetime import datetime, timezone

    try:
        interval_sec = _parse_interval(interval)
    except ValueError:
        err.print(f"Invalid interval '{interval}'. Use e.g. 30s, 5m, 1h.")
        raise typer.Exit(1)

    rich_console.print(f"\n[bold]Watching[/bold] [cyan]{path}[/cyan]  "
                       f"[dim]every {interval}[/dim]  —  Ctrl+C to stop\n")

    try:
        while True:
            ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
            rich_console.print(f"[dim]\\[{ts}][/dim] Checking...")

            try:
                snap = _load_snapshot(path, ref)
            except NoSnapshotError:
                _no_snapshot_exit(path)
            except FileNotFoundError as exc:
                err.print(str(exc))
                raise typer.Exit(1)

            df = _load(path)
            findings = detect_drift(
                snap["profile"], df,
                skip_columns=_parse_skip(skip),
                psi_warn=psi_warn, psi_crit=psi_crit,
                js_warn=js_warn, js_crit=js_crit,
                null_warn=null_warn, null_crit=null_crit,
            )

            if findings:
                render_drift_report(findings, snap["profile"]["row_count"], len(df),
                                    snapshot_date=snap.get("created_at", ""))
                if notify:
                    from .notifier import notify as _notify
                    from .api import DriftResult
                    result = DriftResult(findings=findings,
                                        ref_row_count=snap["profile"]["row_count"],
                                        cur_row_count=len(df))
                    try:
                        _notify(result, notify, source=path)
                        rich_console.print("[dim]Notification sent.[/dim]")
                    except Exception as exc:
                        err.print(f"Notification failed: {exc}")
            else:
                crit = sum(1 for f in findings if f.severity.value == "critical")
                rich_console.print(f"  [green]No drift detected.[/green]")

            next_ts = datetime.now(timezone.utc).fromtimestamp(
                time.time() + interval_sec, tz=timezone.utc
            ).strftime("%H:%M:%S")
            rich_console.print(f"  [dim]Next check at {next_ts} UTC[/dim]\n")
            time.sleep(interval_sec)

    except KeyboardInterrupt:
        rich_console.print("\n[dim]Watch stopped.[/dim]\n")


def main() -> None:
    import sys
    if sys.platform == "win32":
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    app()


if __name__ == "__main__":
    main()
