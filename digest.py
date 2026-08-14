from collections import defaultdict
from datetime import date as date_cls, datetime, timedelta


def build_digest_entry(record: dict) -> dict:
    summary = record["summary"]

    entry = {
        "id": summary["activityId"],
        "date": summary["startTimeLocal"].split(" ")[0],
        "type": summary["activityType"]["typeKey"],
    }

    duration_s = summary.get("duration")
    if duration_s is not None:
        entry["duration_min"] = round(duration_s / 60, 1)

    distance_m = summary.get("distance")
    if distance_m:
        entry["distance_km"] = round(distance_m / 1000, 1)

        moving_duration_s = summary.get("movingDuration")
        if moving_duration_s:
            entry["avg_pace"] = _format_pace(distance_m, moving_duration_s)

    avg_hr = summary.get("averageHR")
    if avg_hr is not None:
        entry["avg_hr"] = round(avg_hr)

    max_hr = summary.get("maxHR")
    if max_hr is not None:
        entry["max_hr"] = round(max_hr)

    elevation_gain = summary.get("elevationGain")
    if elevation_gain:
        entry["elevation_gain_m"] = round(elevation_gain)

    calories = summary.get("calories")
    if calories is not None:
        entry["calories"] = round(calories)

    training_effect = summary.get("trainingEffectLabel")
    if training_effect:
        entry["training_effect"] = training_effect

    hr_zone_seconds = _extract_hr_zone_seconds(record.get("hr_zones"))
    if hr_zone_seconds is not None:
        entry["hr_zone_seconds"] = hr_zone_seconds

    weather = record.get("weather")
    if weather:
        temp = weather.get("temp")
        if temp is not None:
            entry["temp_c"] = temp

    return entry


def _format_pace(distance_m: float, moving_duration_s: float) -> str:
    seconds_per_km = moving_duration_s / (distance_m / 1000)
    minutes, seconds = divmod(round(seconds_per_km), 60)
    return f"{minutes}:{seconds:02d}/km"


def _extract_hr_zone_seconds(hr_zones: list[dict] | None) -> list[int] | None:
    if not hr_zones:
        return None
    by_zone = {z["zoneNumber"]: z["secsInZone"] for z in hr_zones}
    return [round(by_zone.get(n, 0.0)) for n in range(1, 6)]


def build_weekly_rollups(entries: list[dict]) -> list[dict]:
    by_week: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for entry in entries:
        entry_date = datetime.strptime(entry["date"], "%Y-%m-%d").date()
        iso_year, iso_week, _ = entry_date.isocalendar()
        by_week[(iso_year, iso_week)].append(entry)

    return [
        _build_week_rollup(iso_year, iso_week, week_entries)
        for (iso_year, iso_week), week_entries in sorted(by_week.items())
    ]


def _build_week_rollup(iso_year: int, iso_week: int, entries: list[dict]) -> dict:
    start = date_cls.fromisocalendar(iso_year, iso_week, 1)
    end = start + timedelta(days=6)

    rollup = {
        "week": f"{iso_year}-W{iso_week:02d}",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "activity_count": len(entries),
    }

    for field in ("distance_km", "duration_min", "elevation_gain_m"):
        total = _sum_field(entries, field)
        if total is not None:
            rollup[f"total_{field}"] = total

    rollup["by_type"] = _build_by_type(entries)

    avg_hr = _avg_field(entries, "avg_hr")
    if avg_hr is not None:
        rollup["avg_hr"] = avg_hr

    hr_zone_seconds = _sum_hr_zone_seconds(entries)
    if hr_zone_seconds is not None:
        rollup["hr_zone_seconds"] = hr_zone_seconds

    training_effect_counts = _count_training_effects(entries)
    if training_effect_counts:
        rollup["training_effect_counts"] = training_effect_counts

    return rollup


def _sum_field(entries: list[dict], field: str) -> float | None:
    values = [e[field] for e in entries if field in e]
    if not values:
        return None
    return round(sum(values), 1)


def _avg_field(entries: list[dict], field: str) -> int | None:
    values = [e[field] for e in entries if field in e]
    if not values:
        return None
    return round(sum(values) / len(values))


def _sum_hr_zone_seconds(entries: list[dict]) -> list[int] | None:
    zone_lists = [e["hr_zone_seconds"] for e in entries if "hr_zone_seconds" in e]
    if not zone_lists:
        return None
    totals = [0, 0, 0, 0, 0]
    for zones in zone_lists:
        for i, seconds in enumerate(zones):
            totals[i] += seconds
    return totals


def _count_training_effects(entries: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in entries:
        label = entry.get("training_effect")
        if label:
            counts[label] = counts.get(label, 0) + 1
    return counts


def _build_by_type(entries: list[dict]) -> dict[str, dict]:
    by_type: dict[str, dict] = {}
    for entry in entries:
        stats = by_type.setdefault(entry["type"], {"count": 0})
        stats["count"] += 1
        for field in ("distance_km", "duration_min"):
            if field in entry:
                stats[field] = round(stats.get(field, 0.0) + entry[field], 1)
    return by_type
