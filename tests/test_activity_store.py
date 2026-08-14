import json

from activity_store import known_activity_ids, save_activity


def test_known_activity_ids_empty_when_dir_missing(tmp_path):
    missing_dir = tmp_path / "activities"
    assert known_activity_ids(missing_dir) == set()


def test_known_activity_ids_reads_existing_json_stems(tmp_path):
    activities_dir = tmp_path / "activities"
    activities_dir.mkdir()
    (activities_dir / "111.json").write_text("{}")
    (activities_dir / "222.json").write_text("{}")
    (activities_dir / "111.gpx").write_bytes(b"<gpx></gpx>")

    assert known_activity_ids(activities_dir) == {"111", "222"}


def test_save_activity_writes_json_and_gpx(tmp_path):
    activities_dir = tmp_path / "activities"
    record = {"summary": {"activityId": 123}}

    save_activity(activities_dir, "123", record, gpx_bytes=b"<gpx>route</gpx>")

    json_path = activities_dir / "123.json"
    gpx_path = activities_dir / "123.gpx"
    assert json.loads(json_path.read_text()) == record
    assert gpx_path.read_bytes() == b"<gpx>route</gpx>"


def test_save_activity_skips_gpx_when_none(tmp_path):
    activities_dir = tmp_path / "activities"

    save_activity(activities_dir, "456", {"summary": {}}, gpx_bytes=None)

    assert (activities_dir / "456.json").exists()
    assert not (activities_dir / "456.gpx").exists()


def test_digest_index_exists_false_when_missing(tmp_path):
    from activity_store import digest_index_exists

    assert digest_index_exists(tmp_path / "activities") is False


def test_append_digest_entry_creates_and_appends_jsonl(tmp_path):
    from activity_store import append_digest_entry

    activities_dir = tmp_path / "activities"
    append_digest_entry(activities_dir, {"id": 1, "date": "2025-01-01", "type": "running"})
    append_digest_entry(activities_dir, {"id": 2, "date": "2025-01-02", "type": "yoga"})

    lines = (activities_dir / "index.jsonl").read_text().splitlines()
    assert [json.loads(line) for line in lines] == [
        {"id": 1, "date": "2025-01-01", "type": "running"},
        {"id": 2, "date": "2025-01-02", "type": "yoga"},
    ]


def test_write_digest_index_overwrites_full_file(tmp_path):
    from activity_store import append_digest_entry, write_digest_index

    activities_dir = tmp_path / "activities"
    append_digest_entry(activities_dir, {"id": 99, "date": "2025-01-01", "type": "running"})

    write_digest_index(
        activities_dir,
        [
            {"id": 1, "date": "2025-01-01", "type": "running"},
            {"id": 2, "date": "2025-01-02", "type": "yoga"},
        ],
    )

    lines = (activities_dir / "index.jsonl").read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["id"] == 1


def test_read_digest_entries_empty_when_missing(tmp_path):
    from activity_store import read_digest_entries

    assert read_digest_entries(tmp_path / "activities") == []


def test_read_digest_entries_round_trips_appended_entries(tmp_path):
    from activity_store import append_digest_entry, read_digest_entries

    activities_dir = tmp_path / "activities"
    append_digest_entry(activities_dir, {"id": 1, "date": "2025-01-01", "type": "running"})
    append_digest_entry(activities_dir, {"id": 2, "date": "2025-01-02", "type": "yoga"})

    assert read_digest_entries(activities_dir) == [
        {"id": 1, "date": "2025-01-01", "type": "running"},
        {"id": 2, "date": "2025-01-02", "type": "yoga"},
    ]


def test_write_weekly_rollups_writes_one_line_per_rollup(tmp_path):
    from activity_store import write_weekly_rollups

    activities_dir = tmp_path / "activities"
    write_weekly_rollups(
        activities_dir,
        [{"week": "2025-W11", "activity_count": 1}, {"week": "2025-W12", "activity_count": 2}],
    )

    lines = (activities_dir / "weekly.jsonl").read_text().splitlines()
    assert [json.loads(line)["week"] for line in lines] == ["2025-W11", "2025-W12"]


def test_load_all_activity_records_sorted_by_start_time(tmp_path):
    from activity_store import load_all_activity_records

    activities_dir = tmp_path / "activities"
    activities_dir.mkdir()
    (activities_dir / "2.json").write_text(
        json.dumps({"summary": {"activityId": 2, "startTimeLocal": "2025-01-02 08:00:00"}})
    )
    (activities_dir / "1.json").write_text(
        json.dumps({"summary": {"activityId": 1, "startTimeLocal": "2025-01-01 08:00:00"}})
    )

    records = load_all_activity_records(activities_dir)

    assert [activity_id for activity_id, _record in records] == ["1", "2"]


def test_load_all_activity_records_skips_unreadable_file(tmp_path, capsys):
    from activity_store import load_all_activity_records

    activities_dir = tmp_path / "activities"
    activities_dir.mkdir()
    (activities_dir / "1.json").write_text(
        json.dumps({"summary": {"activityId": 1, "startTimeLocal": "2025-01-01 08:00:00"}})
    )
    (activities_dir / "2.json").write_text("{not valid json")

    records = load_all_activity_records(activities_dir)

    assert [activity_id for activity_id, _record in records] == ["1"]
    assert "Warning" in capsys.readouterr().out


def test_load_all_activity_records_empty_when_dir_missing(tmp_path):
    from activity_store import load_all_activity_records

    assert load_all_activity_records(tmp_path / "activities") == []
