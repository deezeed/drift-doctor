import pytest
from pathlib import Path
from drift_doctor.config import load_config

try:
    import tomli as _tomli
    HAS_TOMLI = True
except ImportError:
    import sys
    HAS_TOMLI = sys.version_info >= (3, 11)


@pytest.fixture
def cfg_dir(tmp_path):
    return tmp_path


def test_no_file_returns_defaults(cfg_dir):
    cfg = load_config(cfg_dir)
    assert cfg["psi_warn"] == 0.1
    assert cfg["psi_crit"] == 0.25
    assert cfg["js_warn"] == 0.1
    assert cfg["js_crit"] == 0.3
    assert cfg["null_warn"] == 0.05
    assert cfg["null_crit"] == 0.15
    assert cfg["skip"] == ""
    assert cfg["notify"] == ""
    assert cfg["fail_on"] == "critical"


@pytest.mark.skipif(not HAS_TOMLI, reason="tomli not installed")
def test_partial_thresholds(cfg_dir):
    (cfg_dir / ".driftdoctor.toml").write_text(
        "[thresholds]\npsi_warn = 0.2\npsi_crit = 0.5\n", encoding="utf-8"
    )
    cfg = load_config(cfg_dir)
    assert cfg["psi_warn"] == 0.2
    assert cfg["psi_crit"] == 0.5
    assert cfg["js_warn"] == 0.1   # default unchanged


@pytest.mark.skipif(not HAS_TOMLI, reason="tomli not installed")
def test_defaults_section(cfg_dir):
    (cfg_dir / ".driftdoctor.toml").write_text(
        '[defaults]\nskip = "id,ts"\nfail_on = "any"\n', encoding="utf-8"
    )
    cfg = load_config(cfg_dir)
    assert cfg["skip"] == "id,ts"
    assert cfg["fail_on"] == "any"
    assert cfg["psi_warn"] == 0.1  # default unchanged


@pytest.mark.skipif(not HAS_TOMLI, reason="tomli not installed")
def test_full_config(cfg_dir):
    toml = (
        "[thresholds]\n"
        "psi_warn = 0.15\npsi_crit = 0.3\n"
        "js_warn = 0.12\njs_crit = 0.35\n"
        "null_warn = 0.08\nnull_crit = 0.2\n\n"
        "[defaults]\n"
        'skip = "row_id"\n'
        'notify = "https://hooks.example.com/abc"\n'
        'fail_on = "any"\n'
    )
    (cfg_dir / ".driftdoctor.toml").write_text(toml, encoding="utf-8")
    cfg = load_config(cfg_dir)
    assert cfg["psi_warn"] == 0.15
    assert cfg["null_crit"] == 0.2
    assert cfg["skip"] == "row_id"
    assert cfg["notify"] == "https://hooks.example.com/abc"
    assert cfg["fail_on"] == "any"


@pytest.mark.skipif(not HAS_TOMLI, reason="tomli not installed")
def test_empty_toml_returns_defaults(cfg_dir):
    (cfg_dir / ".driftdoctor.toml").write_text("", encoding="utf-8")
    cfg = load_config(cfg_dir)
    assert cfg["psi_warn"] == 0.1
