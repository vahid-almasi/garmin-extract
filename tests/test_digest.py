from digest import build_digest_entry


FULL_RUNNING_RECORD = {
    "summary": {
        "activityId": 18569572375,
        "startTimeLocal": "2025-03-18 19:31:27",
        "activityType": {"typeKey": "running"},
        "duration": 3626.60693359375,
        "distance": 7246.919921875,
        "movingDuration": 3342.0,
        "averageHR": 133.0,
        "maxHR": 159.0,
        "elevationGain": 16.270000010728836,
        "calories": 617.0,
        "trainingEffectLabel": "AEROBIC_BASE",
    },
    "hr_zones": [
        {"zoneNumber": 1, "secsInZone": 237.0, "zoneLowBoundary": 96},
        {"zoneNumber": 2, "secsInZone": 1306.994, "zoneLowBoundary": 115},
        {"zoneNumber": 3, "secsInZone": 1920.725, "zoneLowBoundary": 134},
        {"zoneNumber": 4, "secsInZone": 87.002, "zoneLowBoundary": 153},
        {"zoneNumber": 5, "secsInZone": 0.0, "zoneLowBoundary": 172},
    ],
    "weather": {"temp": 39, "relativeHumidity": 33},
}

INDOOR_NO_WEATHER_RECORD = {
    "summary": {
        "activityId": 555,
        "startTimeLocal": "2025-01-10 07:00:00",
        "activityType": {"typeKey": "indoor_cardio"},
        "duration": 1800.0,
        "distance": 0.0,
        "movingDuration": 0.0,
        "averageHR": 128.0,
        "maxHR": 145.0,
        "elevationGain": 0.0,
        "calories": 250.0,
    },
    "hr_zones": [],
    "weather": {"temp": None, "relativeHumidity": None},
}

YOGA_RECORD = {
    "summary": {
        "activityId": 777,
        "startTimeLocal": "2025-01-11 06:30:00",
        "activityType": {"typeKey": "yoga"},
        "duration": 2100.0,
    },
}


def test_build_digest_entry_full_outdoor_running():
    entry = build_digest_entry(FULL_RUNNING_RECORD)

    assert entry == {
        "id": 18569572375,
        "date": "2025-03-18",
        "type": "running",
        "duration_min": 60.4,
        "distance_km": 7.2,
        "avg_pace": "7:41/km",
        "avg_hr": 133,
        "max_hr": 159,
        "elevation_gain_m": 16,
        "calories": 617,
        "training_effect": "AEROBIC_BASE",
        "hr_zone_seconds": [237, 1307, 1921, 87, 0],
        "temp_c": 39,
    }


def test_build_digest_entry_indoor_activity_omits_distance_elevation_and_weather():
    entry = build_digest_entry(INDOOR_NO_WEATHER_RECORD)

    assert entry == {
        "id": 555,
        "date": "2025-01-10",
        "type": "indoor_cardio",
        "duration_min": 30.0,
        "avg_hr": 128,
        "max_hr": 145,
        "calories": 250,
    }
    assert "distance_km" not in entry
    assert "avg_pace" not in entry
    assert "elevation_gain_m" not in entry
    assert "hr_zone_seconds" not in entry
    assert "temp_c" not in entry
    assert "training_effect" not in entry


def test_build_digest_entry_yoga_no_distance_no_hr_no_weather_keys():
    entry = build_digest_entry(YOGA_RECORD)

    assert entry == {
        "id": 777,
        "date": "2025-01-11",
        "type": "yoga",
        "duration_min": 35.0,
    }
