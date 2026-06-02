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

from .detector import detect_drift, diff_profiles
from .profiler import profile_dataframe
from .reporter import console as rich_console
from .reporter import render_drift_report, render_snapshot_summary
from .snapshot import load_latest_snapshot, save_snapshot

app = typer.Typer(
    name="drift-doctor",
    help="Monitor datasets for schema and distribution drift.",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
)
err = Console(stderr=True, style="bold red", legacy_windows=False)


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
) -> None:
    """Compare current dataset against the latest snapshot and report drift."""
    try:
        snap = _load_snapshot(path, ref)
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

    use_json = format == OutputFormat.json or bool(output_file)
    if use_json:
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
) -> None:
    """Run drift check then get AI-powered root-cause diagnosis via Anthropic API."""
    from .diagnose import run_diagnosis

    try:
        snap = _load_snapshot(path, ref)
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

    raise typer.Exit(1 if findings else 0)


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
