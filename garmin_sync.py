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
