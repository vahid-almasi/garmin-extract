# Digest & Weekly Rollups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `activities/index.jsonl` (one digest line per activity) and `activities/weekly.jsonl` (one ISO-week rollup per line), built and kept up to date automatically by `sync()`, so Claude can review long training history from two small files instead of opening every activity JSON.

**Architecture:** A new pure-function module `digest.py` extracts a digest dict from a full activity record and aggregates digest dicts into weekly rollups. `activity_store.py` gains file I/O helpers for the two new files plus a bulk reader for rebuilding from existing activity files. `garmin_sync.py` wires both into `sync()`: rebuild the index from disk if missing, append a digest line per newly synced activity, recompute `weekly.jsonl` whenever the index changed.

**Tech Stack:** Python 3.14+, stdlib only (`json`, `pathlib`, `datetime`, `collections`), pytest with `tmp_path` fixtures — no new dependencies.

## Global Constraints

- Python 3.14+ (per project `README.md`).
- No new third-party dependencies — stdlib only for this feature.
- Digest/rollup files are JSONL (one JSON object per line), not a JSON array.
- Weeks are ISO weeks (Monday–Sunday), labeled `"YYYY-Www"` (e.g. `"2025-W12"`).
- A digest/rollup field is **omitted when not applicable, never written as `null` or `0`** for a field that doesn't apply to that activity.
- Corrupt/unreadable files during a rebuild scan are skipped with a `print("Warning: ...")`, matching the existing resilient-skip pattern in `garmin_sync.sync()` — never abort the whole operation.
- `index.jsonl` is append-only during normal sync (mirrors the existing "never delete or overwrite" behavior for `{id}.json`/`.gpx`). `weekly.jsonl` is fully rewritten each time it's recomputed.
- Full spec: `docs/design/2026-08-06-digest-and-weekly-rollups-design.md`.

---

### Task 1: `digest.py` — `build_digest_entry`

**Files:**
- Create: `digest.py`
- Test: `tests/test_digest.py`

**Interfaces:**
- Produces: `build_digest_entry(record: dict) -> dict`. `record` has the same shape already written to `{id}.json` by `activity_store.save_activity`: `{"summary": dict, "details": ..., "splits": ..., "split_summaries": ..., "hr_zones": list[dict] | None, "weather": dict | None}`. Only `record["summary"]`, `record.get("hr_zones")`, and `record.get("weather")` are read by this function.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_digest.py`:

```python
from digest import build_digest_entry


FULL_RUNNING_RECORD = {
    "summary": {
        "activityId": 18569572375,
        "startTimeLocal": "2025-03-18 19:31:27",
        "activityType": {"typeKey": "running"},
        "duration": 3626.60693359375,
        "distance": 7246.919921875,
        "movingDuration": 3342.0,
        "averageHR": 133.0,
        "maxHR": 159.0,
        "elevationGain": 16.270000010728836,
        "calories": 617.0,
        "trainingEffectLabel": "AEROBIC_BASE",
    },
    "hr_zones": [
        {"zoneNumber": 1, "secsInZone": 237.0, "zoneLowBoundary": 96},
        {"zoneNumber": 2, "secsInZone": 1306.994, "zoneLowBoundary": 115},
        {"zoneNumber": 3, "secsInZone": 1920.725, "zoneLowBoundary": 134},
        {"zoneNumber": 4, "secsInZone": 87.002, "zoneLowBoundary": 153},
        {"zoneNumber": 5, "secsInZone": 0.0, "zoneLowBoundary": 172},
    ],
    "weather": {"temp": 39, "relativeHumidity": 33},
}

INDOOR_NO_WEATHER_RECORD = {
    "summary": {
        "activityId": 555,
        "startTimeLocal": "2025-01-10 07:00:00",
        "activityType": {"typeKey": "indoor_cardio"},
        "duration": 1800.0,
        "distance": 0.0,
        "movingDuration": 0.0,
        "averageHR": 128.0,
        "maxHR": 145.0,
        "elevationGain": 0.0,
        "calories": 250.0,
    },
    "hr_zones": [],
    "weather": {"temp": None, "relativeHumidity": None},
}

YOGA_RECORD = {
    "summary": {
        "activityId": 777,
        "startTimeLocal": "2025-01-11 06:30:00",
        "activityType": {"typeKey": "yoga"},
        "duration": 2100.0,
    },
}


def test_build_digest_entry_full_outdoor_running():
    entry = build_digest_entry(FULL_RUNNING_RECORD)

    assert entry == {
        "id": 18569572375,
        "date": "2025-03-18",
        "type": "running",
        "duration_min": 60.4,
        "distance_km": 7.2,
        "avg_pace": "7:41/km",
        "avg_hr": 133,
        "max_hr": 159,
        "elevation_gain_m": 16,
        "calories": 617,
        "training_effect": "AEROBIC_BASE",
        "hr_zone_seconds": [237, 1307, 1921, 87, 0],
        "temp_c": 39,
    }


def test_build_digest_entry_indoor_activity_omits_distance_elevation_and_weather():
    entry = build_digest_entry(INDOOR_NO_WEATHER_RECORD)

    assert entry == {
        "id": 555,
        "date": "2025-01-10",
        "type": "indoor_cardio",
        "duration_min": 30.0,
        "avg_hr": 128,
        "max_hr": 145,
        "calories": 250,
    }
    assert "distance_km" not in entry
    assert "avg_pace" not in entry
    assert "elevation_gain_m" not in entry
    assert "hr_zone_seconds" not in entry
    assert "temp_c" not in entry
    assert "training_effect" not in entry


def test_build_digest_entry_yoga_no_distance_no_hr_no_weather_keys():
    entry = build_digest_entry(YOGA_RECORD)

    assert entry == {
        "id": 777,
        "date": "2025-01-11",
        "type": "yoga",
        "duration_min": 35.0,
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_digest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'digest'` (or `ImportError: cannot import name 'build_digest_entry'`).

- [ ] **Step 3: Write the implementation**

Create `digest.py`:

```python
def build_digest_entry(record: dict) -> dict:
    summary = record["summary"]

    entry = {
        "id": summary["activityId"],
        "date": summary["startTimeLocal"].split(" ")[0],
        "type": summary["activityType"]["typeKey"],
    }

    duration_s = summary.get("duration")
    if duration_s:
        entry["duration_min"] = round(duration_s / 60, 1)

    distance_m = summary.get("distance")
    if distance_m:
        entry["distance_km"] = round(distance_m / 1000, 1)

        moving_duration_s = summary.get("movingDuration")
        if moving_duration_s:
            entry["avg_pace"] = _format_pace(distance_m, moving_duration_s)

    avg_hr = summary.get("averageHR")
    if avg_hr:
        entry["avg_hr"] = round(avg_hr)

    max_hr = summary.get("maxHR")
    if max_hr:
        entry["max_hr"] = round(max_hr)

    elevation_gain = summary.get("elevationGain")
    if elevation_gain:
        entry["elevation_gain_m"] = round(elevation_gain)

    calories = summary.get("calories")
    if calories:
        entry["calories"] = round(calories)

    training_effect = summary.get("trainingEffectLabel")
    if training_effect:
        entry["training_effect"] = training_effect

    hr_zone_seconds = _extract_hr_zone_seconds(record.get("hr_zones"))
    if hr_zone_seconds is not None:
        entry["hr_zone_seconds"] = hr_zone_seconds

    weather = record.get("weather")
    if weather:
        temp = weather.get("temp")
        if temp is not None:
            entry["temp_c"] = temp

    return entry


def _format_pace(distance_m: float, moving_duration_s: float) -> str:
    seconds_per_km = moving_duration_s / (distance_m / 1000)
    minutes, seconds = divmod(round(seconds_per_km), 60)
    return f"{minutes}:{seconds:02d}/km"


def _extract_hr_zone_seconds(hr_zones: list[dict] | None) -> list[int] | None:
    if not hr_zones:
        return None
    by_zone = {z["zoneNumber"]: z["secsInZone"] for z in hr_zones}
    return [round(by_zone.get(n, 0.0)) for n in range(1, 6)]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_digest.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add digest.py tests/test_digest.py
git commit -m "feat: add build_digest_entry for per-activity digest lines"
```

---

### Task 2: `digest.py` — `build_weekly_rollups`

**Files:**
- Modify: `digest.py`
- Test: `tests/test_digest.py`

**Interfaces:**
- Consumes: digest dicts shaped like the output of `build_digest_entry` from Task 1 (always has `id`/`date`/`type`; other keys present only when applicable).
- Produces: `build_weekly_rollups(entries: list[dict]) -> list[dict]`, sorted ascending by ISO week.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_digest.py`:

```python
from digest import build_weekly_rollups


def test_build_weekly_rollups_groups_and_aggregates_one_week():
    entries = [
        {
            "id": 1,
            "date": "2025-03-17",
            "type": "running",
            "distance_km": 10.0,
            "duration_min": 50.0,
            "avg_pace": "5:00/km",
            "avg_hr": 150,
            "training_effect": "AEROBIC_BASE",
            "hr_zone_seconds": [100, 200, 300, 0, 0],
        },
        {
            "id": 2,
            "date": "2025-03-19",
            "type": "yoga",
            "duration_min": 35.0,
            "training_effect": "RECOVERY",
        },
    ]

    rollups = build_weekly_rollups(entries)

    assert rollups == [
        {
            "week": "2025-W12",
            "start_date": "2025-03-17",
            "end_date": "2025-03-23",
            "activity_count": 2,
            "total_distance_km": 10.0,
            "total_duration_min": 85.0,
            "by_type": {
                "running": {"count": 1, "distance_km": 10.0, "duration_min": 50.0},
                "yoga": {"count": 1, "duration_min": 35.0},
            },
            "avg_hr": 150,
            "hr_zone_seconds": [100, 200, 300, 0, 0],
            "training_effect_counts": {"AEROBIC_BASE": 1, "RECOVERY": 1},
        }
    ]


def test_build_weekly_rollups_week_boundary_and_sort_order():
    entries = [
        {
            "id": 1,
            "date": "2025-03-17",  # Monday, W12
            "type": "running",
            "distance_km": 10.0,
            "duration_min": 50.0,
        },
        {
            "id": 2,
            "date": "2025-03-16",  # Sunday, still W11
            "type": "running",
            "distance_km": 5.0,
            "duration_min": 25.0,
            "avg_hr": 140,
        },
    ]

    rollups = build_weekly_rollups(entries)

    assert [r["week"] for r in rollups] == ["2025-W11", "2025-W12"]
    assert rollups[0] == {
        "week": "2025-W11",
        "start_date": "2025-03-10",
        "end_date": "2025-03-16",
        "activity_count": 1,
        "total_distance_km": 5.0,
        "total_duration_min": 25.0,
        "by_type": {"running": {"count": 1, "distance_km": 5.0, "duration_min": 25.0}},
        "avg_hr": 140,
    }


def test_build_weekly_rollups_empty_input():
    assert build_weekly_rollups([]) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_digest.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_weekly_rollups'`

- [ ] **Step 3: Write the implementation**

Append to `digest.py`:

```python
from collections import defaultdict
from datetime import date as date_cls, datetime, timedelta


def build_weekly_rollups(entries: list[dict]) -> list[dict]:
    by_week: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for entry in entries:
        entry_date = datetime.strptime(entry["date"], "%Y-%m-%d").date()
        iso_year, iso_week, _ = entry_date.isocalendar()
        by_week[(iso_year, iso_week)].append(entry)

    return [
        _build_week_rollup(iso_year, iso_week, week_entries)
        for (iso_year, iso_week), week_entries in sorted(by_week.items())
    ]


def _build_week_rollup(iso_year: int, iso_week: int, entries: list[dict]) -> dict:
    start = date_cls.fromisocalendar(iso_year, iso_week, 1)
    end = start + timedelta(days=6)

    rollup = {
        "week": f"{iso_year}-W{iso_week:02d}",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "activity_count": len(entries),
    }

    for field in ("distance_km", "duration_min", "elevation_gain_m"):
        total = _sum_field(entries, field)
        if total is not None:
            rollup[f"total_{field}"] = total

    rollup["by_type"] = _build_by_type(entries)

    avg_hr = _avg_field(entries, "avg_hr")
    if avg_hr is not None:
        rollup["avg_hr"] = avg_hr

    hr_zone_seconds = _sum_hr_zone_seconds(entries)
    if hr_zone_seconds is not None:
        rollup["hr_zone_seconds"] = hr_zone_seconds

    training_effect_counts = _count_training_effects(entries)
    if training_effect_counts:
        rollup["training_effect_counts"] = training_effect_counts

    return rollup


def _sum_field(entries: list[dict], field: str) -> float | None:
    values = [e[field] for e in entries if field in e]
    if not values:
        return None
    return round(sum(values), 1)


def _avg_field(entries: list[dict], field: str) -> int | None:
    values = [e[field] for e in entries if field in e]
    if not values:
        return None
    return round(sum(values) / len(values))


def _sum_hr_zone_seconds(entries: list[dict]) -> list[int] | None:
    zone_lists = [e["hr_zone_seconds"] for e in entries if "hr_zone_seconds" in e]
    if not zone_lists:
        return None
    totals = [0, 0, 0, 0, 0]
    for zones in zone_lists:
        for i, seconds in enumerate(zones):
            totals[i] += seconds
    return totals


def _count_training_effects(entries: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in entries:
        label = entry.get("training_effect")
        if label:
            counts[label] = counts.get(label, 0) + 1
    return counts


def _build_by_type(entries: list[dict]) -> dict[str, dict]:
    by_type: dict[str, dict] = {}
    for entry in entries:
        stats = by_type.setdefault(entry["type"], {"count": 0})
        stats["count"] += 1
        for field in ("distance_km", "duration_min"):
            if field in entry:
                stats[field] = round(stats.get(field, 0.0) + entry[field], 1)
    return by_type
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_digest.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add digest.py tests/test_digest.py
git commit -m "feat: add build_weekly_rollups for ISO-week aggregation"
```

---

### Task 3: `activity_store.py` — digest file I/O

**Files:**
- Modify: `activity_store.py`
- Test: `tests/test_activity_store.py`

**Interfaces:**
- Produces:
  - `digest_index_exists(activities_dir: Path) -> bool`
  - `append_digest_entry(activities_dir: Path, entry: dict) -> None`
  - `write_digest_index(activities_dir: Path, entries: list[dict]) -> None`
  - `read_digest_entries(activities_dir: Path) -> list[dict]`
  - `write_weekly_rollups(activities_dir: Path, rollups: list[dict]) -> None`
  - `load_all_activity_records(activities_dir: Path) -> list[tuple[str, dict]]` — `(activity_id, record)` pairs, sorted ascending by `summary.startTimeLocal`, skipping unreadable files.
- Consumes: nothing new from other tasks (pure file I/O over `Path` and `dict`/`list`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_activity_store.py`:

```python
def test_digest_index_exists_false_when_missing(tmp_path):
    from activity_store import digest_index_exists

    assert digest_index_exists(tmp_path / "activities") is False


def test_append_digest_entry_creates_and_appends_jsonl(tmp_path):
    from activity_store import append_digest_entry

    activities_dir = tmp_path / "activities"
    append_digest_entry(activities_dir, {"id": 1, "date": "2025-01-01", "type": "running"})
    append_digest_entry(activities_dir, {"id": 2, "date": "2025-01-02", "type": "yoga"})

    lines = (activities_dir / "index.jsonl").read_text().splitlines()
    assert [json.loads(line) for line in lines] == [
        {"id": 1, "date": "2025-01-01", "type": "running"},
        {"id": 2, "date": "2025-01-02", "type": "yoga"},
    ]


def test_write_digest_index_overwrites_full_file(tmp_path):
    from activity_store import append_digest_entry, write_digest_index

    activities_dir = tmp_path / "activities"
    append_digest_entry(activities_dir, {"id": 99, "date": "2025-01-01", "type": "running"})

    write_digest_index(
        activities_dir,
        [
            {"id": 1, "date": "2025-01-01", "type": "running"},
            {"id": 2, "date": "2025-01-02", "type": "yoga"},
        ],
    )

    lines = (activities_dir / "index.jsonl").read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["id"] == 1


def test_read_digest_entries_empty_when_missing(tmp_path):
    from activity_store import read_digest_entries

    assert read_digest_entries(tmp_path / "activities") == []


def test_read_digest_entries_round_trips_appended_entries(tmp_path):
    from activity_store import append_digest_entry, read_digest_entries

    activities_dir = tmp_path / "activities"
    append_digest_entry(activities_dir, {"id": 1, "date": "2025-01-01", "type": "running"})
    append_digest_entry(activities_dir, {"id": 2, "date": "2025-01-02", "type": "yoga"})

    assert read_digest_entries(activities_dir) == [
        {"id": 1, "date": "2025-01-01", "type": "running"},
        {"id": 2, "date": "2025-01-02", "type": "yoga"},
    ]


def test_write_weekly_rollups_writes_one_line_per_rollup(tmp_path):
    from activity_store import write_weekly_rollups

    activities_dir = tmp_path / "activities"
    write_weekly_rollups(
        activities_dir,
        [{"week": "2025-W11", "activity_count": 1}, {"week": "2025-W12", "activity_count": 2}],
    )

    lines = (activities_dir / "weekly.jsonl").read_text().splitlines()
    assert [json.loads(line)["week"] for line in lines] == ["2025-W11", "2025-W12"]


def test_load_all_activity_records_sorted_by_start_time(tmp_path):
    from activity_store import load_all_activity_records

    activities_dir = tmp_path / "activities"
    activities_dir.mkdir()
    (activities_dir / "2.json").write_text(
        json.dumps({"summary": {"activityId": 2, "startTimeLocal": "2025-01-02 08:00:00"}})
    )
    (activities_dir / "1.json").write_text(
        json.dumps({"summary": {"activityId": 1, "startTimeLocal": "2025-01-01 08:00:00"}})
    )

    records = load_all_activity_records(activities_dir)

    assert [activity_id for activity_id, _record in records] == ["1", "2"]


def test_load_all_activity_records_skips_unreadable_file(tmp_path, capsys):
    from activity_store import load_all_activity_records

    activities_dir = tmp_path / "activities"
    activities_dir.mkdir()
    (activities_dir / "1.json").write_text(
        json.dumps({"summary": {"activityId": 1, "startTimeLocal": "2025-01-01 08:00:00"}})
    )
    (activities_dir / "2.json").write_text("{not valid json")

    records = load_all_activity_records(activities_dir)

    assert [activity_id for activity_id, _record in records] == ["1"]
    assert "Warning" in capsys.readouterr().out


def test_load_all_activity_records_empty_when_dir_missing(tmp_path):
    from activity_store import load_all_activity_records

    assert load_all_activity_records(tmp_path / "activities") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_activity_store.py -v`
Expected: FAIL with `ImportError` for each new symbol.

- [ ] **Step 3: Write the implementation**

Append to `activity_store.py` (and add `INDEX_FILENAME`/`WEEKLY_FILENAME` constants near the top, after imports):

```python
INDEX_FILENAME = "index.jsonl"
WEEKLY_FILENAME = "weekly.jsonl"


def digest_index_exists(activities_dir: Path) -> bool:
    return (Path(activities_dir) / INDEX_FILENAME).exists()


def append_digest_entry(activities_dir: Path, entry: dict) -> None:
    activities_dir = Path(activities_dir)
    activities_dir.mkdir(parents=True, exist_ok=True)
    with (activities_dir / INDEX_FILENAME).open("a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def write_digest_index(activities_dir: Path, entries: list[dict]) -> None:
    activities_dir = Path(activities_dir)
    activities_dir.mkdir(parents=True, exist_ok=True)
    lines = "".join(json.dumps(entry, default=str) + "\n" for entry in entries)
    (activities_dir / INDEX_FILENAME).write_text(lines)


def read_digest_entries(activities_dir: Path) -> list[dict]:
    path = Path(activities_dir) / INDEX_FILENAME
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def write_weekly_rollups(activities_dir: Path, rollups: list[dict]) -> None:
    activities_dir = Path(activities_dir)
    activities_dir.mkdir(parents=True, exist_ok=True)
    lines = "".join(json.dumps(rollup, default=str) + "\n" for rollup in rollups)
    (activities_dir / WEEKLY_FILENAME).write_text(lines)


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
        records.append((json_path.stem, record))

    records.sort(key=lambda pair: pair[1].get("summary", {}).get("startTimeLocal", ""))
    return records
```

Add `import json` at the top of `tests/test_activity_store.py` if not already present (it already imports `json`, per existing file — confirm and skip if so).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_activity_store.py -v`
Expected: PASS (all tests, existing + new)

- [ ] **Step 5: Commit**

```bash
git add activity_store.py tests/test_activity_store.py
git commit -m "feat: add digest/weekly-rollup file I/O to activity_store"
```

---

### Task 4: `garmin_sync.py` — `ensure_digest_index`

**Files:**
- Modify: `garmin_sync.py`
- Test: `tests/test_garmin_sync.py`

**Interfaces:**
- Consumes: `activity_store.digest_index_exists`, `activity_store.read_digest_entries`, `activity_store.write_digest_index`, `activity_store.load_all_activity_records` (Task 3); `digest.build_digest_entry` (Task 1).
- Produces: `ensure_digest_index(activities_dir: Path) -> tuple[list[dict], bool]` — returns `(digest_entries, was_rebuilt)`. If `index.jsonl` already exists, reads and returns it with `was_rebuilt=False`. Otherwise rebuilds it from every existing `activities/*.json`, writes it, and returns the new entries with `was_rebuilt=True`. A record that `build_digest_entry` can't process (e.g. missing `"summary"`) is skipped with a warning rather than aborting the rebuild — some existing tests in this repo use bare `{}` placeholder activity files, and real activity files could in principle be malformed too.

- [ ] **Step 1: Write the failing tests**

Add near the top of `tests/test_garmin_sync.py`: `import json` (the file doesn't import it yet).

Append to `tests/test_garmin_sync.py`:

```python
def test_ensure_digest_index_builds_from_existing_activities(tmp_path):
    from garmin_sync import ensure_digest_index

    activities_dir = tmp_path / "activities"
    activities_dir.mkdir()
    record = {
        "summary": {
            "activityId": 1,
            "startTimeLocal": "2025-03-18 19:31:27",
            "activityType": {"typeKey": "running"},
            "duration": 600.0,
        }
    }
    (activities_dir / "1.json").write_text(json.dumps(record))

    entries, was_rebuilt = ensure_digest_index(activities_dir)

    assert was_rebuilt is True
    assert entries == [{"id": 1, "date": "2025-03-18", "type": "running", "duration_min": 10.0}]
    assert json.loads((activities_dir / "index.jsonl").read_text().splitlines()[0]) == entries[0]


def test_ensure_digest_index_reads_existing_without_rebuilding(tmp_path):
    from garmin_sync import ensure_digest_index

    activities_dir = tmp_path / "activities"
    activities_dir.mkdir()
    (activities_dir / "index.jsonl").write_text(
        json.dumps({"id": 1, "date": "2025-01-01", "type": "running"}) + "\n"
    )
    # A stray activity file with no digest entry — must NOT trigger a rebuild
    # since index.jsonl already exists.
    (activities_dir / "2.json").write_text(json.dumps({"summary": {"activityId": 2}}))

    entries, was_rebuilt = ensure_digest_index(activities_dir)

    assert was_rebuilt is False
    assert entries == [{"id": 1, "date": "2025-01-01", "type": "running"}]


def test_ensure_digest_index_skips_record_missing_summary(tmp_path, capsys):
    from garmin_sync import ensure_digest_index

    activities_dir = tmp_path / "activities"
    activities_dir.mkdir()
    (activities_dir / "1.json").write_text(json.dumps({}))
    (activities_dir / "2.json").write_text(
        json.dumps(
            {
                "summary": {
                    "activityId": 2,
                    "startTimeLocal": "2025-01-01 08:00:00",
                    "activityType": {"typeKey": "running"},
                    "duration": 600.0,
                }
            }
        )
    )

    entries, was_rebuilt = ensure_digest_index(activities_dir)

    assert was_rebuilt is True
    assert entries == [{"id": 2, "date": "2025-01-01", "type": "running", "duration_min": 10.0}]
    assert "Warning" in capsys.readouterr().out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_garmin_sync.py -v -k ensure_digest_index`
Expected: FAIL with `ImportError: cannot import name 'ensure_digest_index'`

- [ ] **Step 3: Write the implementation**

In `garmin_sync.py`, update the imports at the top and add the new function. Replace:

```python
from activity_store import known_activity_ids, save_activity
```

with:

```python
from pathlib import Path

from activity_store import (
    digest_index_exists,
    known_activity_ids,
    load_all_activity_records,
    read_digest_entries,
    save_activity,
    write_digest_index,
)
from digest import build_digest_entry
```

(`from pathlib import Path` already exists at the top of the file — don't duplicate it, just add the `activity_store`/`digest` imports next to the existing ones.)

Add this function anywhere after the imports (e.g. directly above `sync`):

```python
def ensure_digest_index(activities_dir: Path) -> tuple[list[dict], bool]:
    activities_dir = Path(activities_dir)
    if digest_index_exists(activities_dir):
        return read_digest_entries(activities_dir), False

    entries = []
    for activity_id, record in load_all_activity_records(activities_dir):
        try:
            entries.append(build_digest_entry(record))
        except (KeyError, TypeError) as e:
            print(f"Warning: skipping activity {activity_id} while building digest: {e}")

    write_digest_index(activities_dir, entries)
    return entries, True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_garmin_sync.py -v -k ensure_digest_index`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add garmin_sync.py tests/test_garmin_sync.py
git commit -m "feat: add ensure_digest_index to rebuild-or-read the digest index"
```

---

### Task 5: `garmin_sync.py` — wire digest/rollups into `sync()`

**Files:**
- Modify: `garmin_sync.py`
- Modify: `tests/test_garmin_sync.py`

**Interfaces:**
- Consumes: `ensure_digest_index` (Task 4), `activity_store.append_digest_entry` / `activity_store.write_weekly_rollups` (Task 3), `digest.build_digest_entry` / `digest.build_weekly_rollups` (Tasks 1–2).
- Produces: `sync()` keeps its existing signature and return value (`list[str]` of newly synced activity IDs) — no change to its public contract, only to its side effects (`index.jsonl`/`weekly.jsonl` now maintained alongside `{id}.json`/`.gpx`).

This task also fixes two existing test fixtures that don't carry enough data for digest building (they predate this feature):
- `make_summary()` only sets `activityId` — `build_digest_entry` needs `startTimeLocal` and `activityType` too.
- `DetailFakeClient.get_activity_hr_in_timezones()` returns `{"zones": []}`, but the real Garmin API (and `digest.build_digest_entry`) expects a **list** of `{"zoneNumber": ..., "secsInZone": ...}` dicts. Fixing the fake to match reality.

- [ ] **Step 1: Update the shared test fixtures**

In `tests/test_garmin_sync.py`, replace the `DetailFakeClient.get_activity_hr_in_timezones` method:

```python
    def get_activity_hr_in_timezones(self, activity_id):
        return {"zones": []}
```

with:

```python
    def get_activity_hr_in_timezones(self, activity_id):
        return []
```

And update the one existing assertion that checks this shape — in `test_fetch_activity_record_assembles_all_detail_pieces`, change:

```python
        "hr_zones": {"zones": []},
```

to:

```python
        "hr_zones": [],
```

Replace `make_summary`:

```python
def make_summary(activity_id):
    return {"activityId": activity_id}
```

with:

```python
def make_summary(activity_id):
    return {
        "activityId": activity_id,
        "startTimeLocal": "2025-01-01 08:00:00",
        "activityType": {"typeKey": "running"},
        "duration": 600.0,
    }
```

- [ ] **Step 2: Run the full suite to confirm the fixture changes alone don't break anything**

Run: `pytest tests/ -v`
Expected: PASS (all existing tests still pass — these fixtures aren't asserted against for their exact content anywhere except the one assertion just updated).

- [ ] **Step 3: Write the failing tests for sync() wiring**

Append to `tests/test_garmin_sync.py`:

```python
def test_sync_writes_digest_entry_and_weekly_rollup_for_new_activity(tmp_path):
    from garmin_sync import sync

    activities_dir = tmp_path / "activities"

    sync(PagedFakeClient([[make_summary(1)]]), activities_dir, page_size=1, request_delay=0)

    index_lines = (activities_dir / "index.jsonl").read_text().splitlines()
    assert len(index_lines) == 1
    assert json.loads(index_lines[0]) == {
        "id": 1,
        "date": "2025-01-01",
        "type": "running",
        "duration_min": 10.0,
    }

    weekly_lines = (activities_dir / "weekly.jsonl").read_text().splitlines()
    assert len(weekly_lines) == 1
    assert json.loads(weekly_lines[0])["activity_count"] == 1


def test_sync_rebuilds_digest_for_preexisting_activities_with_no_new_ones(tmp_path):
    from garmin_sync import sync

    activities_dir = tmp_path / "activities"
    activities_dir.mkdir()
    existing_record = {
        "summary": {
            "activityId": 2,
            "startTimeLocal": "2025-01-01 08:00:00",
            "activityType": {"typeKey": "running"},
            "duration": 600.0,
        }
    }
    (activities_dir / "2.json").write_text(json.dumps(existing_record))
    (activities_dir / ".backfill_complete").touch()

    synced = sync(
        PagedFakeClient([[make_summary(2)]]), activities_dir, page_size=1, request_delay=0
    )

    assert synced == []
    index_lines = (activities_dir / "index.jsonl").read_text().splitlines()
    assert len(index_lines) == 1
    assert json.loads(index_lines[0])["id"] == 2
    weekly_lines = (activities_dir / "weekly.jsonl").read_text().splitlines()
    assert len(weekly_lines) == 1


def test_sync_leaves_weekly_rollup_untouched_when_nothing_new(tmp_path):
    from garmin_sync import sync

    activities_dir = tmp_path / "activities"
    sync(PagedFakeClient([[make_summary(1)]]), activities_dir, page_size=1, request_delay=0)
    weekly_before = (activities_dir / "weekly.jsonl").read_text()

    synced_again = sync(
        PagedFakeClient([[make_summary(1)]]), activities_dir, page_size=1, request_delay=0
    )

    assert synced_again == []
    assert (activities_dir / "weekly.jsonl").read_text() == weekly_before
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/test_garmin_sync.py -v -k "digest_entry_and_weekly or rebuilds_digest or leaves_weekly"`
Expected: FAIL — `index.jsonl`/`weekly.jsonl` don't exist yet (`sync()` doesn't call `ensure_digest_index` yet).

- [ ] **Step 5: Wire it into `sync()`**

In `garmin_sync.py`, update the imports (from Task 4) to also bring in `append_digest_entry` and `write_weekly_rollups`:

```python
from activity_store import (
    append_digest_entry,
    digest_index_exists,
    known_activity_ids,
    load_all_activity_records,
    read_digest_entries,
    save_activity,
    write_digest_index,
    write_weekly_rollups,
)
from digest import build_digest_entry, build_weekly_rollups
```

Replace the body of `sync()`:

```python
def sync(client, activities_dir, page_size: int = 20, request_delay: float = 0.75) -> list[str]:
    activities_dir = Path(activities_dir)
    known_ids = known_activity_ids(activities_dir)
    marker_path = activities_dir / BACKFILL_MARKER_NAME
    is_backfill = not marker_path.exists()
    newly_synced: list[str] = []

    digest_entries, index_was_rebuilt = ensure_digest_index(activities_dir)

    total = call_with_retry(client.count_activities) if is_backfill else None

    start = 0
    while True:
        page = call_with_retry(client.get_activities, start, page_size)
        if not page:
            break

        stop = False
        for summary in page:
            activity_id = str(summary["activityId"])

            if activity_id in known_ids:
                if is_backfill:
                    continue
                stop = True
                break

            try:
                record = fetch_activity_record(client, activity_id, summary)
                gpx_bytes = fetch_gpx(client, activity_id)
            except GarminConnectTooManyRequestsError:
                raise
            except Exception as e:
                print(f"Warning: skipping activity {activity_id} after fetch error: {e}")
                continue

            save_activity(activities_dir, activity_id, record, gpx_bytes)

            digest_entry = build_digest_entry(record)
            append_digest_entry(activities_dir, digest_entry)
            digest_entries.append(digest_entry)

            known_ids.add(activity_id)
            newly_synced.append(activity_id)
            if is_backfill and len(newly_synced) % 10 == 0:
                print(f"Synced {len(newly_synced)}/{total} activities...")
            time.sleep(request_delay)

        if stop:
            break

        start += page_size

    if is_backfill:
        activities_dir.mkdir(parents=True, exist_ok=True)
        marker_path.touch()

    if newly_synced or index_was_rebuilt:
        write_weekly_rollups(activities_dir, build_weekly_rollups(digest_entries))

    return newly_synced
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_garmin_sync.py -v`
Expected: PASS (all tests, existing + new)

- [ ] **Step 7: Run the full suite**

Run: `pytest tests/ -v`
Expected: PASS (every test in the project)

- [ ] **Step 8: Commit**

```bash
git add garmin_sync.py tests/test_garmin_sync.py
git commit -m "feat: maintain index.jsonl and weekly.jsonl automatically during sync"
```

---

## Out of scope (for this plan)

- Subsystem B (new data sources: sleep, resting HR, body battery, weight) — separate spec + plan.
- Subsystem C (automation of the sync trigger) — separate spec + plan.
- Any CLI/flag for forcing a manual rebuild — deleting `index.jsonl`/`weekly.jsonl` and re-running `sync()` already does this, per the spec.
