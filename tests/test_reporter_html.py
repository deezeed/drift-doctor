from __future__ import annotations

from drift_doctor.api import DriftResult
from drift_doctor.detector import DriftFinding, Severity
from drift_doctor.reporter_html import render_html


def _result(critical=2, warn=1) -> DriftResult:
    findings = []
    for i in range(critical):
        findings.append(DriftFinding(
            column=f"col{i}", metric="null_pct", severity=Severity.CRITICAL,
            reference_value=0.0, current_value=0.5, delta=0.5,
            description="drifted", detail=f"0% -> 50% (+50%)",
        ))
    for i in range(warn):
        findings.append(DriftFinding(
            column=f"wcol{i}", metric="js_divergence", severity=Severity.WARN,
            reference_value=None, current_value=None, delta=0.15,
            description="drifted", detail="JS=0.150",
        ))
    return DriftResult(findings=findings, ref_row_count=1000, cur_row_count=1050,
                       snapshot_date="20260101T120000Z")


def test_render_html_returns_string():
    html = render_html(_result(), source="customers.csv")
    assert isinstance(html, str)
    assert html.startswith("<!DOCTYPE html>")


def test_html_contains_source():
    html = render_html(_result(), source="customers.csv")
    assert "customers.csv" in html


def test_html_contains_findings():
    html = render_html(_result(critical=2, warn=1))
    assert "col0" in html
    assert "col1" in html
    assert "wcol0" in html


def test_html_severity_badges():
    html = render_html(_result(critical=1, warn=1))
    assert "badge-critical" in html
    assert "badge-warn" in html


def test_html_no_findings():
    result = DriftResult(findings=[], ref_row_count=100, cur_row_count=100)
    html = render_html(result)
    assert "No drift detected" in html


def test_html_row_counts():
    result = _result()
    html = render_html(result)
    assert "1,050" in html
    assert "1,000" in html


def test_to_html_method():
    result = _result()
    html = result.to_html(source="test.csv")
    assert "test.csv" in html
    assert "<!DOCTYPE html>" in html
