from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

SNAPSHOT_DIR = ".driftdoctor"


class NoSnapshotError(FileNotFoundError):
    """Raised when no reference snapshot exists for a dataset."""
    def __init__(self, source_path: str):
        self.source_path = source_path
        super().__init__(f"No snapshot found for '{Path(source_path).stem}'.")


def save_snapshot(profile: dict, source_path: str, base_dir: Path | None = None) -> Path:
    snapshot_dir = (base_dir or Path()) / SNAPSHOT_DIR
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


def load_latest_snapshot(source_path: str, base_dir: Path | None = None) -> dict:
    source_stem = Path(source_path).stem
    latest_path = (base_dir or Path()) / SNAPSHOT_DIR / f"{source_stem}_latest.json"

    if not latest_path.exists():
        raise NoSnapshotError(source_path)

    return json.loads(latest_path.read_text(encoding="utf-8"))
