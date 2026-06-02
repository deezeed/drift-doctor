# drift-doctor

[![CI](https://github.com/deezeed/drift-doctor/actions/workflows/ci.yml/badge.svg)](https://github.com/deezeed/drift-doctor/actions/workflows/ci.yml)

CLI data drift watchdog with AI diagnosis. Monitors tabular datasets for schema and distribution changes between a reference snapshot and new incoming data, then uses the Anthropic API to explain what changed, why it likely happened, and which downstream consumers are at risk.

```
Row count: 1,000 -> 1,000 (+0, +0.0%)  (snapshot: 20260601T140029Z)
             Drift Findings  (5 issues)

  Sev     Column   Metric   Detail
 ──────────────────────────────────────────────────────
  CRIT    phone    schema   present -> missing
  CRIT    spend    null%    1.6% -> 32.5%  (+30.9%)
  CRIT    age      mean_shift   mean 34.3 -> 49.8  (+15.5)
  WARN    email    schema   new column
  WARN    status   JS-div   JS=0.155
```

## Install

```bash
pip install drift-doctor
```

**Recommended for CLI use — via pipx** (handles PATH automatically):
```bash
pipx install drift-doctor
```

> On Windows, if `drift-doctor` is not found after `pip install`, run `pipx ensurepath` and reopen your terminal, or use `py -m drift_doctor.cli` as a fallback.

Requires Python 3.10+. For AI diagnosis, set `ANTHROPIC_API_KEY` in your environment.

## Commands

### `drift-doctor snapshot <path>`

Profile a dataset and save a reference snapshot to `.driftdoctor/`.

```bash
drift-doctor snapshot data/customers.csv
```

Captures per-column: dtype, null rate, cardinality, numeric stats (mean/std/min/max/quantiles), categorical top-k distribution, and PSI bin edges.

---

### `drift-doctor check <path>`

Compare current data against the latest snapshot and print a severity-ranked report.

```bash
drift-doctor check data/customers.csv
drift-doctor check data/customers.csv --ref .driftdoctor/customers_20260101T120000Z.json
drift-doctor check data/customers.csv --skip customer_id,created_at
```

Detects:
- New or missing columns
- dtype changes
- Null rate shifts (warn >5%, critical >15%)
- Numeric distribution drift via **PSI** (warn >0.10, critical >0.25)
- Categorical distribution drift via **JS-divergence** (warn >0.10, critical >0.30)

Exits with code `1` when critical findings exist (default). Control this with `--fail-on`. Suitable for CI/CD pipelines.

| Flag | Description |
|---|---|
| `--ref`, `-r` | Path to a specific snapshot JSON instead of the auto-detected latest |
| `--skip`, `-s` | Comma-separated columns to exclude (e.g. ID, timestamp columns) |
| `--format`, `-f` | Output format: `table` (default) or `json` |
| `--output-file`, `-o` | Write JSON report to file (implies `--format json`) |
| `--notify`, `-n` | Webhook URL to POST findings — Slack or generic (sent only when findings exist) |
| `--output-file report.html` | Write HTML report (auto-detected by `.html` extension) |
| `--since` | Use snapshot closest to this age: `7d`, `24h`, `30m` |
| `--fail-on` | Exit 1 on: `critical` (default) or `any` findings |
| `--psi-warn` / `--psi-crit` | PSI thresholds (default: 0.10 / 0.25) |
| `--js-warn` / `--js-crit` | JS-divergence thresholds (default: 0.10 / 0.30) |
| `--null-warn` / `--null-crit` | Null-rate delta thresholds (default: 0.05 / 0.15) |

---

### `drift-doctor diff <snapshot_a> <snapshot_b>`

Compare two snapshot files directly — no raw data needed.

```bash
drift-doctor diff .driftdoctor/customers_20260101T120000Z.json \
                  .driftdoctor/customers_20260201T120000Z.json
drift-doctor diff snap_a.json snap_b.json --skip customer_id --format json
```

Useful for comparing historical snapshots or validating that a re-run produced the same profile.

| Flag | Description |
|---|---|
| `--skip`, `-s` | Comma-separated columns to exclude |
| `--format`, `-f` | Output format: `table` (default) or `json` |

---

### `drift-doctor diagnose <path>`

Runs `check`, then sends **only aggregated statistics** (no raw data) to the Anthropic API and prints a structured AI diagnosis.

```bash
drift-doctor diagnose data/customers.csv \
  --ref .driftdoctor/customers_20260101T120000Z.json \
  --skip customer_id \
  --consumers "revenue-dashboard,ml-churn-model,crm-sync"
```

The AI response covers:
1. Plain-English summary of what changed
2. Ranked root-cause hypotheses
3. Which downstream consumers are most at risk
4. Recommended immediate actions

| Flag | Description |
|---|---|
| `--ref`, `-r` | Specific snapshot JSON |
| `--skip`, `-s` | Columns to exclude |
| `--consumers`, `-c` | Comma-separated downstream consumer names for targeted risk assessment |
| `--psi-warn` / `--psi-crit` | PSI thresholds |
| `--js-warn` / `--js-crit` | JS-divergence thresholds |
| `--null-warn` / `--null-crit` | Null-rate delta thresholds |

**Privacy guarantee:** raw data rows never leave the machine. Only column names, metric deltas, and severity labels are sent to the API.

## Demo

```bash
# Generate demo data with intentional drift
python demo/generate_demo_data.py

cd demo

# Take a reference snapshot
drift-doctor snapshot reference.csv

# Check the drifted dataset
drift-doctor check current.csv --ref .driftdoctor/reference_latest.json --skip customer_id

# Full AI diagnosis
drift-doctor diagnose current.csv \
  --ref .driftdoctor/reference_latest.json \
  --skip customer_id \
  --consumers "revenue-dashboard,ml-churn-model,crm-sync"

# Compare two snapshots without raw data
drift-doctor diff .driftdoctor/reference_latest.json .driftdoctor/current_latest.json --skip customer_id

# Export findings as JSON or HTML
drift-doctor check current.csv --skip customer_id --output-file report.json
drift-doctor check current.csv --skip customer_id --output-file report.html

# Continuous monitoring — check every 30 seconds
drift-doctor watch current.csv --interval 30s --skip customer_id
```

The demo dataset has these intentional drift signals:

| Column | Change |
|---|---|
| `phone` | column removed |
| `email` | new column added |
| `age` | mean shifted 35 → 50 (PSI ~3.0) |
| `spend` | null rate 1.6% → 32.5% |
| `status` | churned share 10% → 60% |

## Continuous monitoring

### `drift-doctor watch <path>`

Check a dataset repeatedly at a fixed interval. Runs immediately, then waits.

```bash
# Check every hour, alert on Slack when drift is found
drift-doctor watch data/customers.csv --interval 1h --notify https://hooks.slack.com/...

# Check every 5 minutes, skip ID columns
drift-doctor watch data/customers.csv --interval 5m --skip customer_id,created_at
```

Supports `s` (seconds), `m` (minutes), `h` (hours). Press Ctrl+C to stop.

---

### GitHub Actions data quality gate

Fail CI when a PR introduces data drift. The HTML report is uploaded as an artifact.

```yaml
- name: Install drift-doctor
  run: pip install drift-doctor

- name: Check for drift
  run: |
    drift-doctor check data/customers.csv \
      --skip customer_id,created_at \
      --output-file drift-report.html

- name: Upload drift report
  if: always()
  uses: actions/upload-artifact@v4
  with:
    name: drift-report
    path: drift-report.html
```

A full example workflow is at [`.github/workflows/data-quality.yml.example`](.github/workflows/data-quality.yml.example).

---

## Python API

Use drift-doctor directly in notebooks, Airflow DAGs, or ML pipelines — no CLI required.

```python
from drift_doctor import snapshot, check_drift, diff_snapshots

# Save a reference snapshot (written to data/.driftdoctor/)
snapshot("data/customers.csv")

# Check for drift
result = check_drift("data/customers.csv")

print(result.has_drift)          # True / False
print(result.summary)            # {"critical": 2, "warn": 1, "total": 3}
print(result.critical)           # list of DriftFinding objects
print(result.findings[0].column) # "age"
print(result.findings[0].detail) # "mean 34.3 -> 49.8  (+15.5)"

# Raise in a pipeline if critical drift is found
result.raise_on_critical()

# Send Slack alert (only fires when findings exist)
result.notify("https://hooks.slack.com/services/T.../B.../xxx", source="customers.csv")

# Generic webhook — n8n, Zapier, Teams, custom endpoint
result.notify("https://my-endpoint.example.com/hook")

# Use a specific snapshot file
result = check_drift("data/customers.csv",
                     ref="data/.driftdoctor/customers_20260101T120000Z.json",
                     skip=["customer_id"])

# Compare two snapshots without raw data
result = diff_snapshots("snap_jan.json", "snap_feb.json")
```

**`DriftResult` properties:**

| Property | Type | Description |
|---|---|---|
| `findings` | `list[DriftFinding]` | All findings, sorted critical-first |
| `critical` | `list[DriftFinding]` | Critical-severity findings only |
| `warnings` | `list[DriftFinding]` | Warn-severity findings only |
| `has_drift` | `bool` | True if any findings exist |
| `summary` | `dict` | `{"critical": N, "warn": N, "total": N}` |
| `raise_on_critical()` | — | Raises `RuntimeError` if critical findings exist |
| `notify(url, source="")` | — | POST findings to Slack or generic webhook (no-op if no findings) |
| `to_html(source="")` | `str` | Generate a standalone HTML report |

## Supported formats

CSV (`.csv`) and Parquet (`.parquet`, `.pq`).

## Run tests

```bash
pip install -e ".[dev]"
pytest
```

## Stack

- [pandas](https://pandas.pydata.org/) + [pyarrow](https://arrow.apache.org/docs/python/) — data loading
- [typer](https://typer.tiangolo.com/) — CLI
- [rich](https://rich.readthedocs.io/) — terminal output
- [Anthropic SDK](https://github.com/anthropics/anthropic-sdk-python) — AI diagnosis (model: `claude-sonnet-4-6`)
