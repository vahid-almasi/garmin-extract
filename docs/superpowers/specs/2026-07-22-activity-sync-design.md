# Activity Sync Design

Date: 2026-07-22

## Goal

Extend `index.py` from a one-shot "fetch last 10 activities" script into a repeatable
sync that pulls full-detail Garmin activity data into local files, incrementally,
without duplicating or deleting anything. This is the data foundation for a future
LLM chat layer that will help with marathon training advice (pace/splits/HR
analysis, run-by-run detail lookup).

## Storage layout

```
activities/
  {activityId}.json   # metadata + details + splits + HR zones + weather
  {activityId}.gpx     # GPS route (omitted if the activity has no GPS, e.g. indoor cardio)
```

One JSON + one GPX file per activity. Each JSON is self-contained, making it a
natural unit for an LLM/RAG layer to read individually later.

## Per-activity JSON contents

All fields come from methods confirmed to exist on the installed `garminconnect`
`Garmin` client:

- `summary` — the matching entry from `get_activities(start, limit)`
- `details` — `get_activity_details(activity_id)`
- `splits` — `get_activity_splits(activity_id)`
- `split_summaries` — `get_activity_split_summaries(activity_id)`
- `hr_zones` — `get_activity_hr_in_timezones(activity_id)`
- `weather` — `get_activity_weather(activity_id)` (best-effort; stored as `null` if
  Garmin has no weather data for that activity — not every activity has it)

GPX file comes from `download_activity(activity_id, dl_fmt=Garmin.ActivityDownloadFormat.GPX)`.
If that raises/returns nothing usable (e.g. indoor activity with no GPS track), skip
writing the `.gpx` file — this is expected, not an error condition.

## Sync algorithm

1. On start, scan `activities/*.json` on disk → build a set of known activity IDs
   (dedup key).
2. Page through `get_activities(start, limit=20)`, newest activities first, 20 per page.
3. For each activity in a page, in order:
   - If its ID is already known: **stop the entire sync** — everything older is
     already synced (activities come back newest-first, so once we hit a known one,
     nothing further back can be new).
   - If unknown: fetch full detail (the 5 calls above) + GPX, write both files, add
     ID to the known set.
4. Special case: if the known-ID set is empty at the start (first-ever run), do not
   stop early — keep paging until `get_activities` returns an empty page. This
   performs a full backfill of all history exactly once.
5. Sync only ever **adds** files. It never deletes or overwrites an existing
   `{id}.json` or `{id}.gpx`.

## Rate limiting / resilience

A `429` was already observed from Garmin during a normal login in this session, and
full backfill makes ~6 API calls per activity (5 JSON endpoints + 1 GPX download), so:

- A small delay (0.5–1s) between the per-activity detail calls to avoid bursting.
- On a 429 (`GarminConnectTooManyRequestsError` or equivalent), back off — sleep and
  retry a bounded number of times — instead of letting the whole run crash.
- Files are written per-activity as the loop progresses (not batched at the end), so
  an interrupted run (crash, rate limit exhaustion, Ctrl-C) simply resumes from where
  it left off on the next invocation — no lost progress, no redundant re-fetching of
  already-saved activities.

## Script structure

Kept as a single file (`index.py`) at this scale:

- `load_known_ids() -> set[str]` — scan `activities/` for existing `{id}.json`
- `save_activity(activity_id, client)` — fetch all detail pieces, write JSON + GPX
  for one activity
- `sync(client)` — the paging/stop-condition loop described above, calls
  `save_activity` for each new ID
- `main()` — log in, call `sync`

## Out of scope (for this spec)

- The LLM/chat layer itself — this spec only covers getting clean, deduplicated
  data onto disk for that layer to consume later.
- Scheduling/automation (cron, launchd) — script is run manually for now.
- A query/index layer over the stored files — deferred until the chat layer design.
