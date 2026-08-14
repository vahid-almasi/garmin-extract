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
