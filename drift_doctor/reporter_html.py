from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .api import DriftResult

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: #f5f5f5; color: #1a1a1a; font-size: 14px; }
.wrap { max-width: 860px; margin: 32px auto; padding: 0 16px 48px; }
h1 { font-size: 20px; font-weight: 700; margin-bottom: 4px; }
.meta { color: #666; font-size: 13px; margin-bottom: 24px; }
.cards { display: flex; gap: 12px; margin-bottom: 28px; flex-wrap: wrap; }
.card { background: #fff; border-radius: 8px; padding: 16px 20px;
        flex: 1; min-width: 140px; border-top: 4px solid #ddd; }
.card.crit  { border-color: #e53e3e; }
.card.warn  { border-color: #dd6b20; }
.card.ok    { border-color: #38a169; }
.card.info  { border-color: #3182ce; }
.card .val  { font-size: 28px; font-weight: 700; line-height: 1.1; }
.card .lbl  { font-size: 12px; color: #666; margin-top: 2px; }
.card.crit .val { color: #e53e3e; }
.card.warn .val { color: #dd6b20; }
.card.ok   .val { color: #38a169; }
.card.info .val { color: #3182ce; }
h2 { font-size: 15px; font-weight: 600; margin-bottom: 12px; }
table { width: 100%; border-collapse: collapse; background: #fff;
        border-radius: 8px; overflow: hidden;
        box-shadow: 0 1px 3px rgba(0,0,0,.08); }
thead th { background: #f0f0f0; text-align: left; padding: 10px 14px;
           font-weight: 600; font-size: 12px; text-transform: uppercase;
           letter-spacing: .04em; color: #555; border-bottom: 1px solid #e0e0e0; }
tbody tr:not(:last-child) td { border-bottom: 1px solid #f0f0f0; }
tbody td { padding: 10px 14px; vertical-align: top; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 4px;
         font-size: 11px; font-weight: 700; text-transform: uppercase;
         letter-spacing: .05em; }
.badge-critical { background: #fff5f5; color: #e53e3e; border: 1px solid #feb2b2; }
.badge-warn     { background: #fffaf0; color: #dd6b20; border: 1px solid #fbd38d; }
.no-findings { background: #fff; border-radius: 8px; padding: 32px;
               text-align: center; color: #38a169; font-weight: 600;
               box-shadow: 0 1px 3px rgba(0,0,0,.08); }
.footer { margin-top: 32px; font-size: 12px; color: #999; text-align: center; }
"""


def _badge(severity: str) -> str:
    cls = "badge-critical" if severity == "critical" else "badge-warn"
    return f'<span class="badge {cls}">{severity}</span>'


def render_html(result: DriftResult, source: str = "") -> str:
    """Return a complete HTML report string for a DriftResult."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    title = f"Drift Report — {source}" if source else "Drift Report"
    snap_date = result.snapshot_date or "—"

    row_delta = result.cur_row_count - result.ref_row_count
    row_delta_str = f"{row_delta:+,}" if row_delta != 0 else "0"
    row_card_cls = "warn" if abs(row_delta) / max(result.ref_row_count, 1) > 0.1 else "info"

    crit_count = len(result.critical)
    warn_count = len(result.warnings)

    cards_html = f"""
    <div class="cards">
      <div class="card {'crit' if crit_count else 'ok'}">
        <div class="val">{crit_count}</div>
        <div class="lbl">Critical</div>
      </div>
      <div class="card {'warn' if warn_count else 'ok'}">
        <div class="val">{warn_count}</div>
        <div class="lbl">Warnings</div>
      </div>
      <div class="card {row_card_cls}">
        <div class="val">{result.cur_row_count:,}</div>
        <div class="lbl">Rows (ref: {result.ref_row_count:,}, delta: {row_delta_str})</div>
      </div>
      <div class="card info">
        <div class="val" style="font-size:13px;padding-top:4px">{snap_date}</div>
        <div class="lbl">Snapshot date</div>
      </div>
    </div>"""

    if result.findings:
        rows = ""
        for f in result.findings:
            detail = f.detail or f.description
            rows += (
                f"<tr><td>{_badge(f.severity.value)}</td>"
                f"<td><code>{f.column}</code></td>"
                f"<td>{f.metric}</td>"
                f"<td>{detail}</td>"
                f"<td>{f.delta if f.delta is not None else '—'}</td></tr>\n"
            )
        findings_html = f"""
    <h2>Findings ({len(result.findings)})</h2>
    <table>
      <thead>
        <tr>
          <th>Severity</th><th>Column</th><th>Metric</th>
          <th>Detail</th><th>Delta</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>"""
    else:
        findings_html = '<div class="no-findings">No drift detected</div>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="wrap">
  <h1>{title}</h1>
  <div class="meta">Generated {now}</div>
  {cards_html}
  {findings_html}
  <div class="footer">drift-doctor</div>
</div>
</body>
</html>
"""
