import json
from pathlib import Path


INDEX_FILENAME = "index.jsonl"
WEEKLY_FILENAME = "weekly.jsonl"


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


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = "".join(json.dumps(record, default=str) + "\n" for record in records)
    path.write_text(lines)


def digest_index_exists(activities_dir: Path) -> bool:
    return (Path(activities_dir) / INDEX_FILENAME).exists()


def weekly_rollups_exist(activities_dir: Path) -> bool:
    return (Path(activities_dir) / WEEKLY_FILENAME).exists()


def append_digest_entry(activities_dir: Path, entry: dict) -> None:
    activities_dir = Path(activities_dir)
    activities_dir.mkdir(parents=True, exist_ok=True)
    with (activities_dir / INDEX_FILENAME).open("a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def write_digest_index(activities_dir: Path, entries: list[dict]) -> None:
    _write_jsonl(Path(activities_dir) / INDEX_FILENAME, entries)


def read_digest_entries(activities_dir: Path) -> list[dict]:
    path = Path(activities_dir) / INDEX_FILENAME
    if not path.exists():
        return []
    entries = []
    for line in path.read_text().splitlines():
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError as e:
            print(f"Warning: skipping unreadable line in {INDEX_FILENAME}: {e}")
    return entries


def write_weekly_rollups(activities_dir: Path, rollups: list[dict]) -> None:
    _write_jsonl(Path(activities_dir) / WEEKLY_FILENAME, rollups)


def load_all_activity_records(activities_dir: Path) -> list[tuple[str, dict]]:
    activities_dir = Path(activities_dir)
    if not activities_dir.exists():
        return []

    records = []
    for json_path in sorted(activities_dir.glob("*.json")):
        try:
            record = json.loads(json_path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: skipping unreadable activity file {json_path.name}: {e}")
            continue
        if not isinstance(record, dict):
            print(f"Warning: skipping activity file {json_path.name}: not a JSON object")
            continue
        records.append((json_path.stem, record))

    records.sort(key=lambda pair: pair[1].get("summary", {}).get("startTimeLocal", ""))
    return records
