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


def test_fetch_activity_record_propagates_exhausted_rate_limit(monkeypatch):
    from garmin_sync import fetch_activity_record

    monkeypatch.setattr("garmin_sync.time.sleep", lambda s: None)

    class RateLimitedWeatherClient(DetailFakeClient):
        def get_activity_weather(self, activity_id):
            raise GarminConnectTooManyRequestsError("rate limited")

    with pytest.raises(GarminConnectTooManyRequestsError):
        fetch_activity_record(RateLimitedWeatherClient(), "1", {"activityId": 1})


def test_fetch_gpx_propagates_exhausted_rate_limit(monkeypatch):
    from garmin_sync import fetch_gpx

    monkeypatch.setattr("garmin_sync.time.sleep", lambda s: None)

    class RateLimitedGpsClient(DetailFakeClient):
        def download_activity(self, activity_id, dl_fmt=None):
            raise GarminConnectTooManyRequestsError("rate limited")

    with pytest.raises(GarminConnectTooManyRequestsError):
        fetch_gpx(RateLimitedGpsClient(), "1")


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
