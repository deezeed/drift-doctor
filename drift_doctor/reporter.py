from __future__ import annotations

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .detector import METRIC_LABELS, DriftFinding, Severity

console = Console(legacy_windows=False)

_COLORS = {Severity.OK: "green", Severity.WARN: "yellow", Severity.CRITICAL: "red"}
_LABELS = {Severity.OK: "OK  ", Severity.WARN: "WARN", Severity.CRITICAL: "CRIT"}


def render_snapshot_summary(profile: dict, path: str) -> None:
    console.print(f"\n[bold green]Snapshot saved[/bold green] — [cyan]{path}[/cyan]")
    console.print(f"  Rows     : [white]{profile['row_count']:,}[/white]")
    console.print(f"  Columns  : [white]{profile['column_count']}[/white]\n")

    table = Table(title="Column Profiles", box=box.SIMPLE_HEAD, show_lines=False)
    table.add_column("Column", style="cyan", no_wrap=True)
    table.add_column("Type")
    table.add_column("Null %", justify="right")
    table.add_column("Cardinality", justify="right")
    table.add_column("Key Stats")

    for name, col in profile["columns"].items():
        null_str = f"{col['null_pct']:.1%}"
        card_str = f"{col['cardinality']:,}"
        if col["col_type"] == "numeric" and col.get("stats"):
            s = col["stats"]
            detail = f"mean={s['mean']:.3g}  std={s['std']:.3g}  [{s['min']:.3g}, {s['max']:.3g}]"
        elif col["col_type"] == "categorical" and col.get("top_values"):
            top = list(col["top_values"].items())[:3]
            detail = "  ".join(f"{k}={v:.0%}" for k, v in top)
        else:
            detail = ""
        table.add_row(name, col["dtype"], null_str, card_str, detail)

    console.print(table)


def _score_color(score: int) -> str:
    if score >= 90:
        return "green"
    if score >= 70:
        return "yellow"
    return "red"


def render_drift_report(
    findings: list[DriftFinding],
    ref_row_count: int,
    cur_row_count: int,
    snapshot_date: str = "",
    score: int | None = None,
) -> None:
    row_delta = cur_row_count - ref_row_count
    row_pct = row_delta / ref_row_count * 100 if ref_row_count else 0

    date_hint = f"  [dim](snapshot: {snapshot_date})[/dim]" if snapshot_date else ""
    console.print(
        f"\n[bold]Row count:[/bold] {ref_row_count:,} -> {cur_row_count:,} "
        f"([{'green' if row_delta >= 0 else 'red'}]{row_delta:+,}[/], {row_pct:+.1f}%)"
        f"{date_hint}"
    )

    if not findings:
        score_str = (
            f"  Drift score: [bold green]{score}/100[/bold green]\n"
            if score is not None else ""
        )
        console.print(
            f"\n[bold green]No drift detected.[/bold green] All columns within normal ranges.\n"
            + score_str
        )
        return

    table = Table(
        title=f"Drift Findings  ({len(findings)} issue{'s' if len(findings) != 1 else ''})",
        box=box.SIMPLE_HEAD,
        show_lines=False,
        expand=False,
    )
    table.add_column("Sev", width=5, no_wrap=True)
    table.add_column("Column", style="cyan", no_wrap=True)
    table.add_column("Metric", no_wrap=True)
    table.add_column("Detail")

    for f in findings:
        color = _COLORS[f.severity]
        label = _LABELS[f.severity]
        metric_label = METRIC_LABELS.get(f.metric, f.metric)
        table.add_row(
            f"[{color}]{label}[/{color}]",
            f.column,
            metric_label,
            f.detail or f.description,
        )

    console.print(table)

    n_crit = sum(1 for f in findings if f.severity == Severity.CRITICAL)
    n_warn = sum(1 for f in findings if f.severity == Severity.WARN)
    parts: list[str] = []
    if n_crit:
        parts.append(f"[bold red]{n_crit} critical[/bold red]")
    if n_warn:
        parts.append(f"[bold yellow]{n_warn} warning{'s' if n_warn != 1 else ''}[/bold yellow]")
    if score is not None:
        c = _score_color(score)
        parts.append(f"Drift score: [{c}]{score}/100[/{c}]")
    if parts:
        console.print(Panel("  ".join(parts), title="Summary", expand=False))
