import json
from pathlib import Path


def known_activity_ids(activities_dir: Path) -> set[str]:
    if not activities_dir.exists():
        return set()
    return {p.stem for p in activities_dir.glob("*.json")}


def save_activity(activities_dir: Path, activity_id: str, record: dict, gpx_bytes: bytes | None) -> None:
    activities_dir.mkdir(parents=True, exist_ok=True)

    json_path = activities_dir / f"{activity_id}.json"
    json_path.write_text(json.dumps(record, indent=2, default=str))

    if gpx_bytes is not None:
        gpx_path = activities_dir / f"{activity_id}.gpx"
        gpx_path.write_bytes(gpx_bytes)
