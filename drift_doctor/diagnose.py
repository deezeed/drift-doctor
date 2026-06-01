"""AI diagnosis layer — sends ONLY aggregated drift statistics to the Anthropic API.
Raw data rows never leave the machine. Only column names, metric deltas,
and severity labels are included in the prompt."""
from __future__ import annotations

import os

import anthropic
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from .detector import DriftFinding, Severity

console = Console(legacy_windows=False)


def _build_prompt(
    findings: list[DriftFinding],
    ref_profile: dict,
    cur_row_count: int,
    consumers: list[str],
) -> str:
    ref_row_count = ref_profile["row_count"]

    lines = [
        "You are a data quality analyst. A dataset was compared to its reference snapshot.",
        "You are given ONLY aggregated statistics — no raw data rows.",
        "",
        f"Row count: {ref_row_count:,} -> {cur_row_count:,} ({cur_row_count - ref_row_count:+,})",
        "",
        "Drift findings (column name, metric, severity, delta/score):",
    ]

    for f in findings:
        sev = f.severity.value.upper()
        delta = f" delta={f.delta:.4f}" if f.delta is not None else ""
        ref = f" ref={f.reference_value}" if f.reference_value is not None else ""
        cur = f" current={f.current_value}" if f.current_value is not None else ""
        lines.append(f"  [{sev}] {f.column} / {f.metric}{ref}{cur}{delta}")

    if consumers:
        lines += ["", "Downstream consumers of this dataset:"]
        lines += [f"  - {c}" for c in consumers]

    lines += [
        "",
        "Respond with four sections using markdown headers:",
        "## What changed",
        "Plain-English summary of the drift findings.",
        "## Root cause hypotheses",
        "Ranked list (most likely first) of plausible causes.",
        "## At-risk consumers",
        "Which downstream consumers are most affected and why. "
        + ("(No consumers specified — give generic advice.)" if not consumers else ""),
        "## Recommended actions",
        "Concrete immediate steps.",
        "",
        "Be concise. No disclaimers.",
    ]
    return "\n".join(lines)


def run_diagnosis(
    findings: list[DriftFinding],
    ref_profile: dict,
    cur_row_count: int,
    consumers: list[str],
) -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        console.print("\n[red]ANTHROPIC_API_KEY not set — skipping AI diagnosis.[/red]\n")
        return

    prompt = _build_prompt(findings, ref_profile, cur_row_count, consumers)

    client = anthropic.Anthropic(api_key=api_key)

    with console.status("[bold blue]Requesting AI diagnosis from Claude...[/bold blue]"):
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )

    diagnosis = message.content[0].text
    console.print(
        Panel(
            Markdown(diagnosis),
            title="[bold blue]AI Diagnosis[/bold blue]",
            border_style="blue",
            padding=(1, 2),
        )
    )
