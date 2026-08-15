# garmin-extract

Syncs activity data from Garmin Connect to local storage. Each activity is saved as a pair of files: a `.json` file with summary, details, splits, HR zones, and weather data, and a `.gpx` file with the GPS track (when available).

## Requirements

- Python 3.12+ (required by the `garminconnect` package)
- A Garmin Connect account

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
python -m garmin_extract
```

On first run, you'll be prompted for your Garmin Connect email and password (hidden input, via `getpass`). It's then saved to your OS keyring — macOS Keychain, Windows Credential Locker, or the Secret Service on desktop Linux — so later runs read it silently with no plaintext credentials on disk and no environment variables to set. This is fully automatic; there's no separate setup step.

If your Garmin account has MFA enabled, you'll also be prompted for a code on first login. That session is cached to `~/.garminconnect`, so later runs won't prompt for MFA again unless the session expires or is deleted.

Activities are saved to the `activities/` directory. A `.backfill_complete` marker file is created there once the initial backfill finishes, so subsequent runs sync incrementally.

To clear saved credentials (e.g. to switch accounts):

```bash
python -m garmin_extract --reset-credentials
```

### Fallback: environment variables

If your OS keyring isn't available — headless servers, CI, cron jobs, Docker containers — set credentials as environment variables instead. This is **only needed when there's no keyring**; on a normal desktop you don't need this at all. Env vars take priority over the keyring and skip the prompt entirely:

```bash
export GARMIN_EMAIL="you@example.com"
export GARMIN_PASSWORD="your-password"
```

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
- **Digest & weekly rollups** — maintains `activities/index.jsonl` (a lightweight per-activity summary) and `activities/weekly.jsonl` (ISO-week training rollups) automatically, so an LLM reviewing your history doesn't need to open every activity file.

## Project Structure

```
.
├── garmin_extract/
│   ├── __main__.py        # Entry point: `python -m garmin_extract`
│   ├── cli.py              # Argument parsing + top-level flow
│   ├── credentials.py       # Keyring/env-var/getpass credential resolution
│   ├── sync.py                # Core sync logic (backfill, incremental sync, retries)
│   ├── activity_store.py       # Reads/writes activity JSON + GPX files
│   └── digest.py                # Builds per-activity digest entries and weekly rollups
├── activities/                  # Synced activity data (gitignored)
│   ├── {id}.json/.gpx            # Per-activity detail + GPS track
│   ├── index.jsonl                # Lightweight per-activity digest (one line each)
│   └── weekly.jsonl                # ISO-week training rollups
└── tests/                         # Test suite
```

## Testing

```bash
pytest
```
