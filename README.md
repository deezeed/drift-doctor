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
  CRIT    age      PSI      mean 34.3 -> 49.8  (PSI=2.969)
  WARN    email    schema   new column
  WARN    status   JS-div   JS=0.155
```

## Install

**Recommended — via pipx** (handles PATH automatically):
```bash
pipx install git+https://github.com/deezeed/drift-doctor.git
```

**Alternative — via pip:**
```bash
pip install git+https://github.com/deezeed/drift-doctor.git
```
> On Windows, if `drift-doctor` is not found after `pip install`, add Python's Scripts directory to your PATH or run `py -m drift_doctor.cli` instead.

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

Exits with code `1` if any findings exist — suitable for CI/CD pipelines.

| Flag | Description |
|---|---|
| `--ref`, `-r` | Path to a specific snapshot JSON instead of the auto-detected latest |
| `--skip`, `-s` | Comma-separated columns to exclude (e.g. ID, timestamp columns) |

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
```

The demo dataset has these intentional drift signals:

| Column | Change |
|---|---|
| `phone` | column removed |
| `email` | new column added |
| `age` | mean shifted 35 → 50 (PSI ~3.0) |
| `spend` | null rate 1.6% → 32.5% |
| `status` | churned share 10% → 60% |

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
- [Anthropic SDK](https://github.com/anthropics/anthropic-sdk-python) — AI diagnosis (model: `claude-sonnet-4-5`)
