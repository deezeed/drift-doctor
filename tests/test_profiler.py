import numpy as np
import pandas as pd
import pytest

from drift_doctor.profiler import profile_dataframe


def test_numeric_col_type():
    df = pd.DataFrame({"age": list(range(20, 70))})
    p = profile_dataframe(df)
    assert p["columns"]["age"]["col_type"] == "numeric"


def test_categorical_col_type():
    df = pd.DataFrame({"status": ["active", "inactive", "churned"]})
    p = profile_dataframe(df)
    assert p["columns"]["status"]["col_type"] == "categorical"


def test_row_and_column_count():
    df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
    p = profile_dataframe(df)
    assert p["row_count"] == 3
    assert p["column_count"] == 2


def test_null_pct():
    df = pd.DataFrame({"x": [1.0, 2.0, None, None, 5.0]})
    p = profile_dataframe(df)
    assert p["columns"]["x"]["null_pct"] == pytest.approx(0.4)


def test_numeric_stats():
    data = list(range(0, 10))  # 0..9, mean=4.5
    df = pd.DataFrame({"v": data})
    p = profile_dataframe(df)
    col = p["columns"]["v"]
    assert col["stats"]["mean"] == pytest.approx(4.5)
    assert col["stats"]["min"] == pytest.approx(0.0)
    assert col["stats"]["max"] == pytest.approx(9.0)


def test_bin_edges_and_proportions_non_null():
    rng = np.random.default_rng(0)
    df = pd.DataFrame({"v": rng.normal(0, 1, 500)})
    p = profile_dataframe(df)
    col = p["columns"]["v"]
    assert col["bin_edges"] is not None
    assert col["bin_proportions"] is not None
    assert abs(sum(col["bin_proportions"]) - 1.0) < 1e-9


def test_all_nulls_numeric():
    # Use explicit float dtype so pandas keeps it numeric despite all-NaN values.
    df = pd.DataFrame({"x": pd.array([float("nan")] * 3, dtype=float)})
    p = profile_dataframe(df)
    col = p["columns"]["x"]
    assert col["null_pct"] == pytest.approx(1.0)
    assert col["col_type"] == "numeric"
    assert col["stats"] is None
    assert col["bin_edges"] is None


def test_categorical_top_values_proportions():
    df = pd.DataFrame({"cat": ["a"] * 60 + ["b"] * 30 + ["c"] * 10})
    p = profile_dataframe(df)
    tv = p["columns"]["cat"]["top_values"]
    assert tv["a"] == pytest.approx(0.6)
    assert tv["b"] == pytest.approx(0.3)
    assert tv["c"] == pytest.approx(0.1)


def test_cardinality():
    df = pd.DataFrame({"x": [1, 1, 2, 2, 3]})
    p = profile_dataframe(df)
    assert p["columns"]["x"]["cardinality"] == 3
