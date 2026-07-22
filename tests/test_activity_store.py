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
