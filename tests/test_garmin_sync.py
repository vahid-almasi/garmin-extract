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
