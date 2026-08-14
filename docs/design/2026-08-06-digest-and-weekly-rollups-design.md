# Digest & Weekly Rollups Design

Date: 2026-08-06

## Goal

`activities/*.json` files are complete but heavy (full Garmin API payloads,
including irrelevant fields like `userRoles`). Reviewing months of training
history means Claude has to open every file individually. This spec adds a
cheap index of the fields that actually matter for
coaching conversations, plus weekly rollups computed from that index — so a
"review my last 6 months" conversation can work from two small files instead
of scanning the full activity archive.

This is subsystem A of a three-part roadmap (digest/rollups, new data
sources, automation). The other two are out of scope here.

## Storage layout

```
activities/
  {activityId}.json    # unchanged, existing per-activity files
  {activityId}.gpx      # unchanged
  index.jsonl            # NEW: one digest line per activity
  weekly.jsonl            # NEW: one rollup line per ISO week
```

`index.jsonl` and `weekly.jsonl` are derived, regenerable data — deleting
either and re-running sync rebuilds them from `activities/*.json`.

## `digest.py` module

Two pure functions, no I/O, no new dependencies:

- `build_digest_entry(record: dict) -> dict` — one activity's full record
  (the same `{summary, details, splits, split_summaries, hr_zones, weather}`
  shape already written by `garmin_sync.py`) → one digest dict.
- `build_weekly_rollups(entries: list[dict]) -> list[dict]` — a list of
  digest dicts → a list of weekly rollup dicts, one per ISO week present in
  the input.

Kept separate from `activity_store.py` (file I/O) and `garmin_sync.py`
(fetch orchestration) so the extraction/aggregation logic can be unit tested
without touching disk or the Garmin client.

## Per-activity digest entry (`index.jsonl`)

One JSON object per line, sourced entirely from fields already present in
`summary` / `hr_zones` / `weather`:

```json
{"id": 18569572375, "date": "2025-03-18", "type": "running", "distance_km": 12.3, "duration_min": 58.4, "avg_pace": "4:45/km", "avg_hr": 152, "max_hr": 178, "elevation_gain_m": 16, "calories": 612, "training_effect": "AEROBIC_BASE", "hr_zone_seconds": [237, 1307, 1921, 87, 0], "temp_c": 4}
```

Field rules:

- `id` (from `summary.activityId`), `date` (from `summary.startTimeLocal`,
  date part only), `type` (from `summary.activityType.typeKey`) are always
  present.
- Every other key is **omitted, not null**, when not meaningful for that
  activity:
  - `duration_min` — included whenever `summary.duration` is present
    (true for essentially every activity, including non-distance types like
    yoga or strength), converted from seconds to minutes.
  - `distance_km` — omitted if `summary.distance` is missing or zero (e.g.
    yoga, strength).
  - `avg_pace` — included whenever `distance_km` is included and
    `movingDuration` is present and non-zero, computed as `min:sec/km`
    from `distance` / `movingDuration`. Omitted (rather than a nonsensical
    `0:00/km`) if `movingDuration` is zero.
  - `avg_hr` / `max_hr` — omitted if `summary.averageHR` / `maxHR` absent.
  - `elevation_gain_m` — omitted if `summary.elevationGain` is missing or
    zero.
  - `calories` — omitted if `summary.calories` absent.
  - `training_effect` — from `summary.trainingEffectLabel`, omitted if
    absent.
  - `hr_zone_seconds` — a 5-element list from the record's `hr_zones`,
    omitted entirely if `hr_zones` has no usable data.
  - `temp_c` — from `weather.temp`, omitted if `weather` is `None` or
    `weather.temp` is `None` (indoor activities).
- Distance/duration are converted from Garmin's raw units (meters, seconds)
  to km / minutes, rounded to 1 decimal place.

## Weekly rollup entry (`weekly.jsonl`)

One JSON object per line, one per ISO week (Mon–Sun) present in
`index.jsonl`:

```json
{"week": "2025-W12", "start_date": "2025-03-17", "end_date": "2025-03-23", "activity_count": 5, "total_distance_km": 42.1, "total_duration_min": 245.3, "total_elevation_gain_m": 310, "by_type": {"running": {"count": 4, "distance_km": 40.5, "duration_min": 210.0}, "yoga": {"count": 1, "duration_min": 35.3}}, "avg_hr": 148, "hr_zone_seconds": [1200, 4300, 3100, 900, 0], "training_effect_counts": {"AEROBIC_BASE": 3, "LACTATE_THRESHOLD": 1}}
```

Aggregation rules:

- Group `index.jsonl` entries by ISO week of `date`.
- `total_distance_km` / `total_duration_min` / `total_elevation_gain_m` —
  sums over entries that have the field; entries missing it don't
  contribute (not treated as zero).
- `by_type` — per-type counts and sums, same omission rule (e.g. a yoga
  entry contributes to `by_type.yoga.count` and `.duration_min` but not
  `.distance_km`).
- `avg_hr` — simple mean over entries that have `avg_hr` (not time-weighted;
  a coarse weekly signal, not a precise metric).
- `hr_zone_seconds` — elementwise sum over entries that have it.
- `training_effect_counts` — count of entries per `training_effect` value
  present that week.

## Trigger point

Both files are maintained automatically as part of `sync()` — no separate
command or manual step:

1. At the start of `sync()`, if `activities/index.jsonl` does not exist,
   scan every existing `activities/*.json`, sorted by `summary.startTimeLocal`,
   and build `index.jsonl` from scratch (one-time backfill for activities
   synced before this feature existed). A file that fails to parse is
   skipped with a warning, same as other resilient-skip behavior in this
   codebase.
2. As each new activity is saved during a normal sync run (backfill or
   incremental), its digest line is appended to `index.jsonl` immediately
   after `save_activity()` succeeds for it.
3. At the end of `sync()`, `weekly.jsonl` is fully recomputed from
   `index.jsonl` and rewritten if any activities were added, the rebuild
   in step 1 ran, or `weekly.jsonl` doesn't exist yet on disk (so deleting
   just `weekly.jsonl` and re-running sync regenerates it even with no
   new activities). This is cheap — aggregating digest lines (bytes
   each), not re-reading full activity JSON/GPX.

`index.jsonl` is append-only in normal operation (mirrors the existing
sync's "never delete or overwrite" behavior for `{id}.json`/`.gpx`).
`weekly.jsonl` is fully rewritten each time, since it's a small derived
aggregate, not append-only data.

Entry order in `index.jsonl` is the order activities were written, not a
guaranteed chronological sort: normal sync appends newest-first (Garmin
pages activities newest-first), while a rebuild-from-disk sorts
oldest-first by `startTimeLocal`. Every entry carries its own `date`
field, so date-based analysis never depends on file order.

## Error handling / edge cases

- Rebuild scan hits a corrupt/unreadable activity JSON → skip with a
  warning, continue (same pattern as existing fetch-failure handling in
  `sync()`).
- A record that fails digest extraction during the live sync loop (e.g. a
  malformed `startTimeLocal`) is skipped with a warning noting the
  activity was saved but not indexed — the gap is recoverable by deleting
  `index.jsonl` to force a full rebuild on the next sync. The same
  applies during a rebuild, and a corrupted line in an existing
  `index.jsonl` is skipped the same way when read.
- Rebuild and rollup recomputation are both pure functions of on-disk data
  → idempotent. Deleting `index.jsonl`/`weekly.jsonl` and re-running sync
  regenerates them deterministically (useful after a `digest.py` schema
  change).
- Activity types with few/no numeric fields (yoga, strength) produce a
  digest entry with just `id`/`date`/`type` plus whatever subset applies —
  no crashes on missing keys, no fabricated zeros.

## Testing

- Unit tests for `build_digest_entry()` against fixture record shapes:
  outdoor running (full fields), indoor activity (no weather/elevation),
  yoga (no distance/pace/HR-zones). Assert correct extraction and correct
  omission of inapplicable fields.
- Unit tests for `build_weekly_rollups()` given synthetic digest entries
  spanning multiple ISO weeks, including a week-boundary case (activity on
  a Monday vs. the immediately preceding Sunday).
- Integration test: `sync()` against a fresh `activities/` dir that already
  has `*.json` files but no `index.jsonl` → asserts rebuild happens and
  both new files are created correctly.
- Integration test: `sync()` run a second time with no new activities on
  the server → asserts `index.jsonl` has no duplicate lines and
  `weekly.jsonl` is unchanged.
- Integration test: `sync()` run a second time with one genuinely new
  activity against a pre-existing `index.jsonl` (the ordinary weekly
  incremental workflow) → asserts the new digest line is appended without
  duplicating or reordering existing lines, and `weekly.jsonl` reflects
  the combined activity count.

## Out of scope (for this spec)

- New data sources (sleep, resting HR, body battery, weight) — subsystem B.
- Automating the sync trigger itself (cron/launchd/MCP wrapper) —
  subsystem C.
- Any change to the existing per-activity `{id}.json`/`.gpx` files or the
  fetch logic in `garmin_sync.py` beyond calling into `digest.py`.
