# Garmin Connect Sync

Syncs activity data from Garmin Connect to local storage. Each activity is saved as a pair of files: a `.json` file with summary, details, splits, HR zones, and weather data, and a `.gpx` file with the GPS track (when available).

## Features

- **Backfill** — on first run, downloads your entire activity history.
- **Incremental sync** — on later runs, only fetches activities newer than what's already stored, stopping as soon as it reaches a known activity.
- **Rate-limit handling** — retries with exponential backoff when Garmin Connect returns a "too many requests" error.
- **Resilient fetches** — skips an activity (with a warning) if it fails to fetch, rather than aborting the whole sync.

## Requirements

- Python 3.14+
- A Garmin Connect account

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration

Set your Garmin Connect credentials as environment variables:

```bash
export GARMIN_EMAIL="you@example.com"
export GARMIN_PASSWORD="your-password"
```

## Usage

```bash
python index.py
```

Activities are saved to the `activities/` directory. A `.backfill_complete` marker file is created there once the initial backfill finishes, so subsequent runs sync incrementally.

## Project Structure

```
.
├── index.py            # Entry point: logs in and runs sync()
├── garmin_sync.py       # Core sync logic (backfill, incremental sync, retries)
├── activity_store.py    # Reads/writes activity JSON + GPX files
├── activities/           # Synced activity data (gitignored)
└── tests/                # Test suite
```

## Testing

```bash
pytest
```
