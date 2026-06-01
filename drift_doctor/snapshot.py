from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

SNAPSHOT_DIR = ".driftdoctor"


def save_snapshot(profile: dict, source_path: str) -> Path:
    snapshot_dir = Path(SNAPSHOT_DIR)
    snapshot_dir.mkdir(exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    source_stem = Path(source_path).stem

    snapshot = {
        "source": str(source_path),
        "created_at": timestamp,
        "profile": profile,
    }

    snapshot_json = json.dumps(snapshot, indent=2)
    versioned_path = snapshot_dir / f"{source_stem}_{timestamp}.json"
    latest_path = snapshot_dir / f"{source_stem}_latest.json"

    versioned_path.write_text(snapshot_json, encoding="utf-8")
    latest_path.write_text(snapshot_json, encoding="utf-8")

    return versioned_path


def load_latest_snapshot(source_path: str) -> dict:
    source_stem = Path(source_path).stem
    latest_path = Path(SNAPSHOT_DIR) / f"{source_stem}_latest.json"

    if not latest_path.exists():
        raise FileNotFoundError(
            f"No snapshot found for '{source_stem}'. "
            f"Run `drift-doctor snapshot {source_path}` first."
        )

    return json.loads(latest_path.read_text(encoding="utf-8"))
