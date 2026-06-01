from __future__ import annotations

from pathlib import Path

import pandas as pd
import typer
from rich.console import Console

from .detector import detect_drift
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
        import json
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
    ref: str = typer.Option(
        "", "--ref", "-r",
        help="Path to a specific snapshot JSON (overrides auto-lookup by file stem)",
    ),
    skip: str = typer.Option(
        "", "--skip", "-s",
        help="Comma-separated column names to exclude from drift detection (e.g. id,created_at)",
    ),
) -> None:
    """Compare current dataset against the latest snapshot and report drift."""
    try:
        snap = _load_snapshot(path, ref)
    except FileNotFoundError as exc:
        err.print(str(exc))
        raise typer.Exit(1)

    df = _load(path)
    findings = detect_drift(snap["profile"], df, skip_columns=_parse_skip(skip))
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
    ref: str = typer.Option(
        "", "--ref", "-r",
        help="Path to a specific snapshot JSON (overrides auto-lookup by file stem)",
    ),
    skip: str = typer.Option(
        "", "--skip", "-s",
        help="Comma-separated column names to exclude from drift detection",
    ),
    consumers: str = typer.Option(
        "", "--consumers", "-c",
        help="Comma-separated downstream consumer names",
    ),
) -> None:
    """Run drift check then get AI-powered root-cause diagnosis via Anthropic API."""
    from .diagnose import run_diagnosis

    try:
        snap = _load_snapshot(path, ref)
    except FileNotFoundError as exc:
        err.print(str(exc))
        raise typer.Exit(1)

    df = _load(path)
    findings = detect_drift(snap["profile"], df, skip_columns=_parse_skip(skip))
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
