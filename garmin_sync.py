import time
from pathlib import Path

from garminconnect import Garmin, GarminConnectTooManyRequestsError

from activity_store import (
    append_digest_entry,
    digest_index_exists,
    known_activity_ids,
    load_all_activity_records,
    read_digest_entries,
    save_activity,
    weekly_rollups_exist,
    write_digest_index,
    write_weekly_rollups,
)
from digest import build_digest_entry, build_weekly_rollups


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
    except GarminConnectTooManyRequestsError:
        raise
    except Exception:
        return None


def fetch_gpx(client, activity_id: str) -> bytes | None:
    try:
        return call_with_retry(
            client.download_activity, activity_id, dl_fmt=Garmin.ActivityDownloadFormat.GPX
        )
    except GarminConnectTooManyRequestsError:
        raise
    except Exception:
        return None


BACKFILL_MARKER_NAME = ".backfill_complete"


def ensure_digest_index(activities_dir: Path) -> tuple[list[dict], bool]:
    activities_dir = Path(activities_dir)
    if digest_index_exists(activities_dir):
        return read_digest_entries(activities_dir), False

    entries = []
    for activity_id, record in load_all_activity_records(activities_dir):
        try:
            entries.append(build_digest_entry(record))
        except Exception as e:
            print(f"Warning: skipping activity {activity_id} while building digest: {e}")

    write_digest_index(activities_dir, entries)
    return entries, True


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

            try:
                digest_entry = build_digest_entry(record)
            except Exception as e:
                print(
                    f"Warning: activity {activity_id} saved but not indexed "
                    f"(delete index.jsonl to rebuild it on the next sync): {e}"
                )
            else:
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

    if newly_synced or index_was_rebuilt or not weekly_rollups_exist(activities_dir):
        write_weekly_rollups(activities_dir, build_weekly_rollups(digest_entries))

    return newly_synced
