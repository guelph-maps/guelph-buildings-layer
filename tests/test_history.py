"""Tests for the gap history record."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config, history  # noqa: E402


@pytest.fixture
def paths(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "HISTORY_PATH", str(tmp_path / "history.jsonl"))
    # Never reach for the published copy from a test.
    monkeypatch.setattr(history, "seed", lambda: False)
    return tmp_path


SUMMARY = {"missing": 900, "small": 600, "plan": 40, "city": 38944,
           "osm_rings": 41000, "osm_date": "2026-10-08 12:00Z", "osm_stale": False}


def test_a_live_run_is_recorded_with_every_field(paths):
    row = history.record(SUMMARY, day="2026-10-08")
    assert row == {"date": "2026-10-08", "osm_date": "2026-10-08 12:00Z",
                   "source": "live", "missing": 900, "small": 600, "plan": 40,
                   "city": 38944, "osm_rings": 41000}
    assert history.load() == [row]


def test_a_rerun_the_same_day_replaces_the_row(paths):
    history.record(SUMMARY, day="2026-10-01")
    history.record(SUMMARY, day="2026-10-08")
    history.record({**SUMMARY, "missing": 850}, day="2026-10-08")
    rows = history.load()
    assert [r["date"] for r in rows] == ["2026-10-01", "2026-10-08"]
    assert rows[-1]["missing"] == 850


def test_a_stale_run_is_not_recorded(paths):
    assert history.record({**SUMMARY, "osm_stale": True}) is None
    assert history.load() == []
