import time

from garminconnect import Garmin, GarminConnectTooManyRequestsError


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
