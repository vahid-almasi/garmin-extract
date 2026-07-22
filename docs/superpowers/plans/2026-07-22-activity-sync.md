# Activity Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `index.py` into a repeatable sync that pulls full-detail Garmin activities (metadata, splits, HR zones, weather, GPX route) into `activities/`, incrementally, without duplicating or deleting anything.

**Architecture:** Two small modules with no network-vs-storage overlap: `activity_store.py` (pure file I/O — no Garmin client) and `garmin_sync.py` (fetch + orchestration, takes a duck-typed client so it's testable without hitting Garmin's real API). `index.py` stays a thin entry point that logs in and calls `sync()`.

**Tech Stack:** Python 3.14 (already in `.venv`), `garminconnect` 0.3.6 (already installed), `pytest` (to be added as a dev dependency).

## Global Constraints

- Storage layout: one `activities/{activityId}.json` + one `activities/{activityId}.gpx` per activity (GPX omitted when the activity has no GPS track).
- Sync must never delete or overwrite an existing `{id}.json`/`.gpx`.
- Page size for `get_activities`: 20.
- Delay between per-activity detail fetches: 0.75s.
- Rate-limit retry: on `GarminConnectTooManyRequestsError`, retry up to 5 attempts with exponential backoff starting at 2.0s.
- First-ever run (no `activities/.backfill_complete` marker) pages through **all** history; every run after that stops as soon as it hits an activity ID it already has stored.

---

### Task 1: Storage layer — `activity_store.py`

**Files:**
- Create: `activity_store.py`
- Create: `conftest.py` (empty — makes project root importable from `tests/`)
- Create: `tests/test_activity_store.py`

**Interfaces:**
- Produces: `known_activity_ids(activities_dir: Path) -> set[str]`
- Produces: `save_activity(activities_dir: Path, activity_id: str, record: dict, gpx_bytes: bytes | None) -> None`

- [ ] **Step 1: Install pytest into the existing venv**

Run: `.venv/bin/pip install pytest --quiet`
Expected: completes with no error (warnings about cache deserialization are fine, as seen in the earlier `garminconnect` install).

- [ ] **Step 2: Create empty root conftest.py**

```python
```

(This file is intentionally empty. Its presence makes pytest add the project root to `sys.path`, so `tests/*.py` can `import activity_store` and `garmin_sync` directly.)

- [ ] **Step 3: Write the failing tests**

```python
# tests/test_activity_store.py
import json

from activity_store import known_activity_ids, save_activity


def test_known_activity_ids_empty_when_dir_missing(tmp_path):
    missing_dir = tmp_path / "activities"
    assert known_activity_ids(missing_dir) == set()


def test_known_activity_ids_reads_existing_json_stems(tmp_path):
    activities_dir = tmp_path / "activities"
    activities_dir.mkdir()
    (activities_dir / "111.json").write_text("{}")
    (activities_dir / "222.json").write_text("{}")
    (activities_dir / "111.gpx").write_bytes(b"<gpx></gpx>")

    assert known_activity_ids(activities_dir) == {"111", "222"}


def test_save_activity_writes_json_and_gpx(tmp_path):
    activities_dir = tmp_path / "activities"
    record = {"summary": {"activityId": 123}}

    save_activity(activities_dir, "123", record, gpx_bytes=b"<gpx>route</gpx>")

    json_path = activities_dir / "123.json"
    gpx_path = activities_dir / "123.gpx"
    assert json.loads(json_path.read_text()) == record
    assert gpx_path.read_bytes() == b"<gpx>route</gpx>"


def test_save_activity_skips_gpx_when_none(tmp_path):
    activities_dir = tmp_path / "activities"

    save_activity(activities_dir, "456", {"summary": {}}, gpx_bytes=None)

    assert (activities_dir / "456.json").exists()
    assert not (activities_dir / "456.gpx").exists()
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_activity_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'activity_store'`

- [ ] **Step 5: Write the implementation**

```python
# activity_store.py
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
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_activity_store.py -v`
Expected: 4 passed

- [ ] **Step 7: Commit**

```bash
git add activity_store.py conftest.py tests/test_activity_store.py
git commit -m "feat: add activity file storage layer"
```

---

### Task 2: Rate-limit retry helper in `garmin_sync.py`

**Files:**
- Create: `garmin_sync.py`
- Create: `tests/test_garmin_sync.py`

**Interfaces:**
- Consumes: nothing from Task 1 yet (this step is self-contained)
- Produces: `call_with_retry(fn, *args, max_retries: int = 5, initial_delay: float = 2.0, **kwargs)`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_garmin_sync.py
import pytest
from garminconnect import GarminConnectTooManyRequestsError

from garmin_sync import call_with_retry


def test_call_with_retry_retries_on_rate_limit(monkeypatch):
    sleeps = []
    monkeypatch.setattr("garmin_sync.time.sleep", lambda s: sleeps.append(s))

    attempts = {"count": 0}

    def flaky():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise GarminConnectTooManyRequestsError("rate limited")
        return "ok"

    result = call_with_retry(flaky, max_retries=5, initial_delay=1.0)

    assert result == "ok"
    assert attempts["count"] == 3
    assert sleeps == [1.0, 2.0]


def test_call_with_retry_raises_after_max_retries(monkeypatch):
    monkeypatch.setattr("garmin_sync.time.sleep", lambda s: None)

    def always_fails():
        raise GarminConnectTooManyRequestsError("rate limited")

    with pytest.raises(GarminConnectTooManyRequestsError):
        call_with_retry(always_fails, max_retries=3, initial_delay=1.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_garmin_sync.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'garmin_sync'`

- [ ] **Step 3: Write the implementation**

```python
# garmin_sync.py
import time

from garminconnect import GarminConnectTooManyRequestsError


def call_with_retry(fn, *args, max_retries: int = 5, initial_delay: float = 2.0, **kwargs):
    delay = initial_delay
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except GarminConnectTooManyRequestsError:
            if attempt == max_retries - 1:
                raise
            time.sleep(delay)
            delay *= 2
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_garmin_sync.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add garmin_sync.py tests/test_garmin_sync.py
git commit -m "feat: add rate-limit retry helper"
```

---

### Task 3: Per-activity fetch functions in `garmin_sync.py`

**Files:**
- Modify: `garmin_sync.py`
- Modify: `tests/test_garmin_sync.py`

**Interfaces:**
- Consumes: `call_with_retry` (Task 2)
- Produces: `fetch_activity_record(client, activity_id: str, summary: dict) -> dict`
- Produces: `fetch_gpx(client, activity_id: str) -> bytes | None`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_garmin_sync.py`:

```python
class DetailFakeClient:
    def get_activity_details(self, activity_id):
        return {"activityId": activity_id, "detail": True}

    def get_activity_splits(self, activity_id):
        return {"splits": []}

    def get_activity_split_summaries(self, activity_id):
        return {"summaries": []}

    def get_activity_hr_in_timezones(self, activity_id):
        return {"zones": []}

    def get_activity_weather(self, activity_id):
        return {"tempC": 20}

    def download_activity(self, activity_id, dl_fmt=None):
        return b"<gpx>route</gpx>"


def test_fetch_activity_record_assembles_all_detail_pieces():
    from garmin_sync import fetch_activity_record

    summary = {"activityId": 1, "activityName": "Morning Run"}
    record = fetch_activity_record(DetailFakeClient(), "1", summary)

    assert record == {
        "summary": summary,
        "details": {"activityId": "1", "detail": True},
        "splits": {"splits": []},
        "split_summaries": {"summaries": []},
        "hr_zones": {"zones": []},
        "weather": {"tempC": 20},
    }


def test_fetch_activity_record_weather_failure_is_null():
    from garmin_sync import fetch_activity_record

    class NoWeatherClient(DetailFakeClient):
        def get_activity_weather(self, activity_id):
            raise RuntimeError("no weather station data")

    record = fetch_activity_record(NoWeatherClient(), "1", {"activityId": 1})

    assert record["weather"] is None


def test_fetch_gpx_returns_bytes():
    from garmin_sync import fetch_gpx

    assert fetch_gpx(DetailFakeClient(), "1") == b"<gpx>route</gpx>"


def test_fetch_gpx_returns_none_on_failure():
    from garmin_sync import fetch_gpx

    class NoGpsClient(DetailFakeClient):
        def download_activity(self, activity_id, dl_fmt=None):
            raise RuntimeError("no GPS data for this activity")

    assert fetch_gpx(NoGpsClient(), "1") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_garmin_sync.py -v`
Expected: FAIL with `ImportError: cannot import name 'fetch_activity_record'`

- [ ] **Step 3: Write the implementation**

Append to `garmin_sync.py`:

```python
from garminconnect import Garmin


def fetch_activity_record(client, activity_id: str, summary: dict) -> dict:
    return {
        "summary": summary,
        "details": call_with_retry(client.get_activity_details, activity_id),
        "splits": call_with_retry(client.get_activity_splits, activity_id),
        "split_summaries": call_with_retry(client.get_activity_split_summaries, activity_id),
        "hr_zones": call_with_retry(client.get_activity_hr_in_timezones, activity_id),
        "weather": _fetch_weather(client, activity_id),
    }


def _fetch_weather(client, activity_id: str) -> dict | None:
    try:
        return call_with_retry(client.get_activity_weather, activity_id)
    except Exception:
        return None


def fetch_gpx(client, activity_id: str) -> bytes | None:
    try:
        return call_with_retry(
            client.download_activity, activity_id, dl_fmt=Garmin.ActivityDownloadFormat.GPX
        )
    except Exception:
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_garmin_sync.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add garmin_sync.py tests/test_garmin_sync.py
git commit -m "feat: add per-activity detail and GPX fetch functions"
```

---

### Task 4: Sync orchestration — `sync()`

**Files:**
- Modify: `garmin_sync.py`
- Modify: `tests/test_garmin_sync.py`

**Interfaces:**
- Consumes: `known_activity_ids`, `save_activity` (Task 1); `fetch_activity_record`, `fetch_gpx` (Task 3)
- Produces: `sync(client, activities_dir: Path, page_size: int = 20, request_delay: float = 0.75) -> list[str]`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_garmin_sync.py`:

```python
class PagedFakeClient(DetailFakeClient):
    def __init__(self, pages):
        self.pages = pages

    def get_activities(self, start, limit):
        index = start // limit
        if index >= len(self.pages):
            return []
        return self.pages[index]


def make_summary(activity_id):
    return {"activityId": activity_id}


def test_first_run_backfills_all_pages(tmp_path):
    from activity_store import known_activity_ids
    from garmin_sync import sync

    pages = [
        [make_summary(3), make_summary(2)],
        [make_summary(1)],
    ]
    activities_dir = tmp_path / "activities"

    synced = sync(PagedFakeClient(pages), activities_dir, page_size=2, request_delay=0)

    assert set(synced) == {"3", "2", "1"}
    assert known_activity_ids(activities_dir) == {"3", "2", "1"}
    assert (activities_dir / ".backfill_complete").exists()


def test_incremental_run_stops_at_first_known_activity(tmp_path):
    from garmin_sync import sync

    activities_dir = tmp_path / "activities"
    activities_dir.mkdir()
    (activities_dir / "2.json").write_text("{}")
    (activities_dir / ".backfill_complete").touch()

    pages = [[make_summary(4), make_summary(3), make_summary(2), make_summary(1)]]

    synced = sync(PagedFakeClient(pages), activities_dir, page_size=4, request_delay=0)

    assert synced == ["4", "3"]
    assert not (activities_dir / "1.json").exists()


def test_interrupted_backfill_resumes_without_marker(tmp_path):
    from garmin_sync import sync

    activities_dir = tmp_path / "activities"
    activities_dir.mkdir()
    (activities_dir / "3.json").write_text("{}")  # saved before an earlier interruption

    pages = [[make_summary(3), make_summary(2)], [make_summary(1)]]

    synced = sync(PagedFakeClient(pages), activities_dir, page_size=2, request_delay=0)

    assert synced == ["2", "1"]
    assert (activities_dir / ".backfill_complete").exists()


def test_gpx_download_failure_still_saves_json(tmp_path):
    from garmin_sync import sync

    class NoGpsPagedClient(PagedFakeClient):
        def download_activity(self, activity_id, dl_fmt=None):
            raise RuntimeError("no GPS data for this activity")

    activities_dir = tmp_path / "activities"

    sync(NoGpsPagedClient([[make_summary(1)]]), activities_dir, page_size=1, request_delay=0)

    assert (activities_dir / "1.json").exists()
    assert not (activities_dir / "1.gpx").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_garmin_sync.py -v`
Expected: FAIL with `ImportError: cannot import name 'sync'`

- [ ] **Step 3: Write the implementation**

Append to `garmin_sync.py`:

```python
from pathlib import Path

from activity_store import known_activity_ids, save_activity

BACKFILL_MARKER_NAME = ".backfill_complete"


def sync(client, activities_dir, page_size: int = 20, request_delay: float = 0.75) -> list[str]:
    activities_dir = Path(activities_dir)
    known_ids = known_activity_ids(activities_dir)
    marker_path = activities_dir / BACKFILL_MARKER_NAME
    is_backfill = not marker_path.exists()
    newly_synced: list[str] = []

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

            record = fetch_activity_record(client, activity_id, summary)
            gpx_bytes = fetch_gpx(client, activity_id)
            save_activity(activities_dir, activity_id, record, gpx_bytes)

            known_ids.add(activity_id)
            newly_synced.append(activity_id)
            time.sleep(request_delay)

        if stop:
            break

        start += page_size

    if is_backfill:
        activities_dir.mkdir(parents=True, exist_ok=True)
        marker_path.touch()

    return newly_synced
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_garmin_sync.py -v`
Expected: 10 passed

- [ ] **Step 5: Run the full test suite**

Run: `.venv/bin/pytest -v`
Expected: 14 passed (4 from Task 1 + 10 from Tasks 2-4)

- [ ] **Step 6: Commit**

```bash
git add garmin_sync.py tests/test_garmin_sync.py
git commit -m "feat: add incremental sync orchestration with backfill support"
```

---

### Task 5: Wire up `index.py` and do a real sync

**Files:**
- Modify: `index.py`

**Interfaces:**
- Consumes: `sync` (Task 4)

- [ ] **Step 1: Rewrite index.py as the entry point**

```python
# index.py
import os
from pathlib import Path

from garminconnect import Garmin

from garmin_sync import sync

ACTIVITIES_DIR = Path(__file__).parent / "activities"


def main():
    client = Garmin(os.environ["GARMIN_EMAIL"], os.environ["GARMIN_PASSWORD"])
    client.login()

    synced = sync(client, ACTIVITIES_DIR)

    print(f"Synced {len(synced)} new activities: {synced}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the full automated test suite one more time**

Run: `.venv/bin/pytest -v`
Expected: 14 passed (confirms the rewrite didn't touch anything the tests cover — `index.py` itself has no automated test since it's a thin wrapper around already-tested `sync()`)

- [ ] **Step 3: Run it for real against the live Garmin account**

Run: `GARMIN_EMAIL='<your email>' GARMIN_PASSWORD='<your password>' .venv/bin/python index.py`
Expected: Since this account already has some activities synced from earlier in the session (if any), this either does a full first-time backfill (if `activities/` doesn't exist yet) or an incremental sync. Watch for `Synced N new activities: [...]` at the end. Because full backfill makes ~6 API calls per activity with a 0.75s gap each, a history of hundreds of activities can take a while — that's expected, not a hang.

- [ ] **Step 4: Verify the files on disk**

Run: `ls activities/ | head -20 && cat activities/.backfill_complete 2>&1; echo; find activities -name '*.json' | wc -l`
Expected: a mix of `{id}.json` / `{id}.gpx` files, the marker file present (empty), and a JSON count matching the "Synced N new activities" count from Step 3 (assuming `activities/` was empty beforehand).

- [ ] **Step 5: Commit**

```bash
git add index.py
git commit -m "feat: wire sync() into the index.py entry point"
```

---

## Self-Review Notes

- **Spec coverage:** storage layout (Task 1), rate limiting/retry (Task 2), full detail fetch incl. GPX (Task 3), backfill-then-incremental sync algorithm with never-delete guarantee (Task 4), real entry point (Task 5) — all spec sections have a corresponding task.
- **Refinement vs. spec:** the spec describes "first run = empty known-ID set." The plan implements this via an explicit `.backfill_complete` marker file instead of checking `len(known_ids) == 0`, because an interrupted first backfill would otherwise leave a non-empty-but-incomplete known-ID set that the plain emptiness check would misread as "already caught up" (see `test_interrupted_backfill_resumes_without_marker`). This is a strictly more robust implementation of the same spec requirement, not a behavior change.
- **Type consistency:** `activity_id` is a `str` everywhere in `garmin_sync.py`/`activity_store.py` (converted from Garmin's `int` via `str(summary["activityId"])` at the one point summaries are read in `sync()`); `sync()`'s `activities_dir` param accepts `Path | str` and normalizes to `Path` at the top, matching how `index.py` calls it (`Path`) and how tests call it (`tmp_path`, already a `Path`).
