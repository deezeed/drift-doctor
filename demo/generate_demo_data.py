"""Generate reference.csv and current.csv with intentional drift for demo purposes.

Drift introduced in current.csv:
  - `age`    : mean shifted from 35 -> 50  (numeric distribution, CRITICAL PSI)
  - `spend`  : null rate 2% -> 35%         (null rate, CRITICAL)
  - `status` : churned share 10% -> 60%    (categorical, CRITICAL JS)
  - `phone`  : column dropped             (missing column, CRITICAL)
  - `email`  : new column added           (new column, WARN)
"""

from pathlib import Path

import numpy as np
import pandas as pd

rng = np.random.default_rng(42)
N = 1000
OUT = Path(__file__).parent


def make_reference() -> pd.DataFrame:
    ids = np.arange(1, N + 1)
    age = rng.normal(35, 8, N).clip(18, 80).astype(int)
    spend = rng.lognormal(mean=5, sigma=1.2, size=N).round(2)
    nulls = rng.random(N) < 0.02
    spend[nulls] = np.nan
    status = rng.choice(["active", "inactive", "churned"], size=N, p=[0.70, 0.20, 0.10])
    country = rng.choice(["US", "EU", "UK"], size=N, p=[0.55, 0.30, 0.15])
    phone = [f"+1-555-{rng.integers(1000,9999)}" for _ in range(N)]
    return pd.DataFrame({
        "customer_id": ids,
        "age": age,
        "spend": spend,
        "status": status,
        "country": country,
        "phone": phone,
    })


def make_current() -> pd.DataFrame:
    ids = np.arange(1001, 2001)
    # age distribution shifted: mean 35 -> 50
    age = rng.normal(50, 8, N).clip(18, 80).astype(int)
    # spend null rate 2% -> 35%
    spend = rng.lognormal(mean=5, sigma=1.2, size=N).round(2)
    nulls = rng.random(N) < 0.35
    spend[nulls] = np.nan
    # status: churned 10% -> 60%
    status = rng.choice(["active", "inactive", "churned"], size=N, p=[0.25, 0.15, 0.60])
    country = rng.choice(["US", "EU", "UK", "AU"], size=N, p=[0.45, 0.25, 0.15, 0.15])
    # phone column removed; email column added
    email = [f"user{i}@example.com" for i in ids]
    return pd.DataFrame({
        "customer_id": ids,
        "age": age,
        "spend": spend,
        "status": status,
        "country": country,
        "email": email,
    })


if __name__ == "__main__":
    ref = make_reference()
    cur = make_current()
    ref.to_csv(OUT / "reference.csv", index=False)
    cur.to_csv(OUT / "current.csv", index=False)
    print(f"Written: {OUT / 'reference.csv'}  ({len(ref)} rows)")
    print(f"Written: {OUT / 'current.csv'}  ({len(cur)} rows)")
    print("\nExpected drift findings:")
    print("  [CRIT] phone        — missing column")
    print("  [CRIT] age          — PSI > 0.25  (mean 35->50)")
    print("  [CRIT] spend        — null rate +33%")
    print("  [CRIT] status       — JS > 0.3   (churned 10%->60%)")
    print("  [WARN] email        — new column")
    print("  [WARN] country      — JS ~0.1-0.3 (new AU category)")
