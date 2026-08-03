# Garmin Connect Sync

Syncs activity data from Garmin Connect to local storage. Each activity is saved as a pair of files: a `.json` file with summary, details, splits, HR zones, and weather data, and a `.gpx` file with the GPS track (when available).

## How I Use This

The goal behind this project is simple: get all of my Garmin data in front of an LLM and talk to it about my training. A coach who can speak any language, never gets tired of explaining the same thing twice, and can reference the exact detail of any run or week on demand is a genuinely useful thing to have — and an LLM with the right data is that coach. This project exists purely to get the data in front of it.

This project has one job: get my Garmin data onto disk in a form an AI can read. It's deliberately not a training app, a dashboard, or anything with a UI — the "app" is a Claude Desktop project, and this repo is just the data pipeline that feeds it.

My actual workflow:

1. Run the sync to pull the latest activities into the `activities/` directory.
2. Give a Claude Desktop project access to that directory, so it can read the full history of my runs — splits, heart rate zones, weather, GPS tracks, all of it.
3. Ask Claude to review my performance and build a plan around a real goal (e.g. training for the Berlin Marathon), based on what my actual training history says about my fitness, not a generic template.
4. Each week, I run the sync again, bring the new activities into the same project, and ask for the next week's plan — informed by how the previous week actually went.

That loop — sync, review, plan, train, repeat — is the whole point. Everything past "get clean data into a folder" is intentionally left to the conversation with Claude rather than built into this repo.

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
