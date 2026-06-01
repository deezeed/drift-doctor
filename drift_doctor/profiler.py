from __future__ import annotations

import numpy as np
import pandas as pd


def _is_numeric(series: pd.Series) -> bool:
    return pd.api.types.is_numeric_dtype(series)


def _profile_numeric(series: pd.Series, n_bins: int = 10) -> dict:
    non_null = series.dropna()
    if len(non_null) == 0:
        return {"stats": None, "bin_edges": None, "bin_proportions": None}

    stats = {
        "mean": float(non_null.mean()),
        "std": float(non_null.std()) if len(non_null) > 1 else 0.0,
        "min": float(non_null.min()),
        "max": float(non_null.max()),
        "q25": float(non_null.quantile(0.25)),
        "q50": float(non_null.quantile(0.50)),
        "q75": float(non_null.quantile(0.75)),
    }

    percentile_points = np.linspace(0, 100, n_bins + 1)
    raw_edges = np.percentile(non_null, percentile_points)
    unique_edges = np.unique(raw_edges)

    if len(unique_edges) >= 2:
        counts, _ = np.histogram(non_null, bins=unique_edges)
        proportions = (counts / len(non_null)).tolist()
        bin_edges = unique_edges.tolist()
    else:
        bin_edges = None
        proportions = None

    return {"stats": stats, "bin_edges": bin_edges, "bin_proportions": proportions}


def _profile_categorical(series: pd.Series, top_k: int = 50) -> dict:
    value_counts = series.value_counts(normalize=True, dropna=True)
    top_values = {str(k): float(v) for k, v in value_counts.head(top_k).items()}
    return {"top_values": top_values}


def profile_dataframe(df: pd.DataFrame) -> dict:
    columns: dict = {}
    for col in df.columns:
        series = df[col]
        col_profile: dict = {
            "dtype": str(series.dtype),
            "null_pct": float(series.isna().mean()),
            "cardinality": int(series.nunique()),
            "count": int(len(series)),
        }
        if _is_numeric(series):
            col_profile.update(_profile_numeric(series))
            col_profile["col_type"] = "numeric"
        else:
            col_profile.update(_profile_categorical(series))
            col_profile["col_type"] = "categorical"
        columns[col] = col_profile

    return {
        "columns": columns,
        "row_count": int(len(df)),
        "column_count": int(len(df.columns)),
    }
