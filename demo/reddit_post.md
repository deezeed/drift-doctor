# Reddit post — r/datascience

**Title:** I built a CLI data drift watchdog in Python — catches schema changes, null spikes, and distribution shifts in one command

---

```
drift-doctor check data/customers.csv --skip customer_id
```

Outputs this in ~300ms:

```
Row count: 1,000 -> 1,000 (+0, +0.0%)  (snapshot: 20260601T140029Z)
             Drift Findings  (5 issues)

  Sev     Column   Metric       Detail
 ──────────────────────────────────────────────────────
  CRIT    phone    schema       present -> missing
  CRIT    spend    null%        1.6% -> 32.5%  (+30.9%)
  CRIT    age      mean_shift   mean 34.3 -> 49.8  (+15.5)
  WARN    email    schema       new column
  WARN    status   JS-div       JS=0.155
```

---

**Why I built it**

I was tired of data issues silently breaking downstream ML models and dashboards. Existing tools like Evidently and Great Expectations are powerful, but they require significant setup — report servers, expectation suites, YAML configs. I wanted something that works in 30 seconds with a single `pip install`.

**drift-doctor vs the alternatives:**

| | drift-doctor | Evidently | Great Expectations |
|---|---|---|---|
| Setup | `pip install`, one command | Dashboard + config | Expectation suite + data docs |
| Use case | Drift monitoring | Drift + quality reports | Data validation rules |
| CI/CD | Exit code 1 on drift | Custom integration | Custom integration |
| AI diagnosis | Yes (Claude) | No | No |

---

**What it detects**

- Schema changes (added/removed columns, dtype changes)
- Null rate shifts (configurable warn/critical thresholds)
- Numeric distribution drift via **PSI** (Population Stability Index)
- Categorical distribution drift via **JS-divergence**

**Four commands:**

```bash
drift-doctor snapshot data.csv          # save reference profile
drift-doctor check data.csv             # compare to snapshot
drift-doctor diagnose data.csv          # check + AI explanation
drift-doctor watch data.csv --interval 1h --notify https://hooks.slack.com/...
```

`watch` runs continuously, sends Slack alerts on drift, and shows next check time.

`diagnose` sends only aggregated stats (never raw rows) to the Anthropic API and returns: what changed, root-cause hypotheses, which downstream consumers are at risk, and recommended actions.

---

**Python API for notebooks and pipelines:**

```python
from drift_doctor import snapshot, check_drift

snapshot("data/customers.csv")
result = check_drift("data/customers.csv", skip=["customer_id"])

print(result.has_drift)     # True
print(result.summary)       # {"critical": 3, "warn": 2, "total": 5}
result.raise_on_critical()  # raises RuntimeError — fail the pipeline
result.notify("https://hooks.slack.com/...")  # Slack alert
result.to_html()            # standalone HTML report
```

GitHub Actions data quality gate — fails CI when a PR introduces drift, uploads HTML report as artifact.

---

**Install:**

```bash
pip install drift-doctor        # or: pipx install drift-doctor
```

Python 3.10+. AI diagnosis requires `ANTHROPIC_API_KEY`. Supports CSV and Parquet.

Code + demo: https://github.com/deezeed/drift-doctor

---

*Would love feedback — especially on the PSI/JS thresholds and whether the watch command covers real monitoring use cases you've run into.*

---

**Visuals to attach:**
- `demo/watch_demo.gif` — animated GIF (attach as main image, Reddit auto-plays)
- `demo/report_screenshot.png` — HTML report screenshot (attach as second image or in comments)
