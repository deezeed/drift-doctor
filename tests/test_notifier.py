from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from drift_doctor.api import DriftResult
from drift_doctor.detector import DriftFinding, Severity
from drift_doctor.notifier import _build_generic_payload, _build_slack_payload, notify


def _finding(col: str, sev: Severity = Severity.CRITICAL) -> DriftFinding:
    return DriftFinding(
        column=col, metric="null_pct", severity=sev,
        reference_value=0.0, current_value=0.5, delta=0.5,
        description=f"{col} drifted", detail=f"{col} detail",
    )


def _result(critical=1, warn=1) -> DriftResult:
    findings = [_finding(f"col{i}") for i in range(critical)]
    findings += [_finding(f"wcol{i}", Severity.WARN) for i in range(warn)]
    return DriftResult(findings=findings, ref_row_count=1000, cur_row_count=1000)


def test_no_request_when_no_drift():
    result = DriftResult(findings=[], ref_row_count=100, cur_row_count=100)
    with patch("urllib.request.urlopen") as mock_open:
        notify(result, "https://hooks.slack.com/fake")
        mock_open.assert_not_called()


def test_slack_payload_structure():
    result = _result(critical=2, warn=1)
    payload = _build_slack_payload(result, "customers.csv")
    assert "blocks" in payload
    header_text = payload["blocks"][0]["text"]["text"]
    assert "customers.csv" in header_text
    body_text = payload["blocks"][1]["text"]["text"]
    assert "2" in body_text


def test_generic_payload_structure():
    result = _result(critical=1, warn=0)
    payload = _build_generic_payload(result, "data.csv")
    assert payload["source"] == "data.csv"
    assert payload["summary"]["critical"] == 1
    assert len(payload["findings"]) == 1
    assert payload["findings"][0]["column"] == "col0"


def test_notify_uses_slack_for_slack_url():
    result = _result()
    with patch("drift_doctor.notifier._post") as mock_post:
        notify(result, "https://hooks.slack.com/services/T123/B456/xxx", source="test.csv")
        mock_post.assert_called_once()
        payload = mock_post.call_args[0][1]
        assert "blocks" in payload


def test_notify_uses_generic_for_other_url():
    result = _result()
    with patch("drift_doctor.notifier._post") as mock_post:
        notify(result, "https://my-webhook.example.com/hook", source="test.csv")
        mock_post.assert_called_once()
        payload = mock_post.call_args[0][1]
        assert "findings" in payload
        assert "blocks" not in payload


def test_result_notify_method():
    result = _result()
    with patch("drift_doctor.notifier._post") as mock_post:
        result.notify("https://hooks.slack.com/fake", source="test.csv")
        mock_post.assert_called_once()
