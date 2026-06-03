from __future__ import annotations

import sys
from pathlib import Path

CONFIG_FILE = ".driftdoctor.toml"

_DEFAULTS: dict = {
    "psi_warn": 0.1,
    "psi_crit": 0.25,
    "js_warn": 0.1,
    "js_crit": 0.3,
    "null_warn": 0.05,
    "null_crit": 0.15,
    "skip": "",
    "notify": "",
    "fail_on": "critical",
}


def _load_toml(path: Path) -> dict:
    if sys.version_info >= (3, 11):
        import tomllib
        with open(path, "rb") as f:
            return tomllib.load(f)
    import tomli
    with open(path, "rb") as f:
        return tomli.load(f)


def load_config(base_dir: Path | None = None) -> dict:
    """Load .driftdoctor.toml from base_dir (or CWD). Returns merged config dict."""
    result = dict(_DEFAULTS)
    config_path = (base_dir or Path()) / CONFIG_FILE
    if not config_path.exists():
        return result

    try:
        data = _load_toml(config_path)
    except ImportError:
        from .reporter import console
        console.print(
            "[yellow]Warning:[/yellow] .driftdoctor.toml found but "
            "tomli is not installed. Run: pip install tomli"
        )
        return result
    except Exception as exc:
        from .reporter import console
        console.print(f"[yellow]Warning:[/yellow] Could not parse {config_path}: {exc}")
        return result

    thresholds = data.get("thresholds", {})
    defaults = data.get("defaults", {})

    for key in ("psi_warn", "psi_crit", "js_warn", "js_crit", "null_warn", "null_crit"):
        if key in thresholds:
            result[key] = float(thresholds[key])

    for key in ("skip", "notify", "fail_on"):
        if key in defaults:
            result[key] = str(defaults[key])

    return result
