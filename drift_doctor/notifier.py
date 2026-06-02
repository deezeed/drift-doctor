from __future__ import annotations

import json
import urllib.request
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .api import DriftResult

_MAX_FINDINGS_SHOWN = 10


def _post(url: str, payload: dict) -> None:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        if resp.status not in (200, 204):
            raise RuntimeError(f"Webhook returned HTTP {resp.status}")


def _build_slack_payload(result: DriftResult, source: str) -> dict:
    label = source or "dataset"
    summary = result.summary
    header = f":x: Drift detected — {label}" if result.critical else f":warning: Drift detected — {label}"
    parts = []
    if summary["critical"]:
        parts.append(f"*{summary['critical']} critical*")
    if summary["warn"]:
        parts.append(f"{summary['warn']} warning{'s' if summary['warn'] != 1 else ''}")
    parts.append(f"({summary['total']} total)")

    lines = ["  ".join(parts), ""]
    for f in result.findings[:_MAX_FINDINGS_SHOWN]:
        sev = "CRIT " if f.severity.value == "critical" else "WARN "
        lines.append(f"`{sev}` *{f.column}* — {f.detail or f.description}")
    if len(result.findings) > _MAX_FINDINGS_SHOWN:
        lines.append(f"_...and {len(result.findings) - _MAX_FINDINGS_SHOWN} more_")

    return {
        "blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": header, "emoji": True}},
            {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)}},
        ]
    }


def _build_generic_payload(result: DriftResult, source: str) -> dict:
    return {
        "source": source,
        "summary": result.summary,
        "findings": [
            {
                "column": f.column,
                "metric": f.metric,
                "severity": f.severity.value,
                "detail": f.detail or f.description,
                "delta": f.delta,
            }
            for f in result.findings
        ],
    }


def notify(result: DriftResult, webhook_url: str, source: str = "") -> None:
    """POST drift findings to a webhook URL.

    Sends only when findings exist. Detects Slack webhooks automatically
    and formats the payload with Block Kit; all other URLs receive a plain
    JSON report.

    Parameters
    ----------
    result:
        The DriftResult to report.
    webhook_url:
        Slack Incoming Webhook URL or any generic HTTP endpoint.
    source:
        Human-readable label for the dataset (e.g. filename). Used in
        the Slack message header.
    """
    if not result.has_drift:
        return

    is_slack = "hooks.slack.com" in webhook_url
    payload = _build_slack_payload(result, source) if is_slack else _build_generic_payload(result, source)
    _post(webhook_url, payload)
