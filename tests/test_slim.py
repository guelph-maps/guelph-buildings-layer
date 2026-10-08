"""Tests for the slim step: which properties survive, and the count guard."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import config  # noqa: E402
import src.slim as slim_mod  # noqa: E402
from src.slim import is_plan, slim, slim_props  # noqa: E402


def test_slim_props_keeps_the_four_useful_fields():
    props = slim_props({
        "OBJECTID": 1, "NAME": None, "GPID": 2000004431.0, "BLDID": 56714.0,
        "MUN": "GUELPH", "SOURCE": "Aerial photography",
        "Shape__Area": 195.02166354547, "Shape__Length": 56.1,
    })
    assert props == {"bldid": 56714, "source": "Aerial photography", "area": 195}


def test_slim_props_carries_a_name_and_tolerates_missing_fields():
    assert slim_props({"NAME": " Metalworks Phase 1 ", "SOURCE": " "}) == \
        {"name": "Metalworks Phase 1"}


@pytest.mark.parametrize("source, expected", [
    ("PLAN", True), (" plan ", True), ("Aerial photography", False),
    ("ORTHO", False), ("", False), (None, False),
])
def test_is_plan(source, expected):
    assert is_plan(source) is expected


def _feature(oid, geom_type="Polygon"):
    x, y = -80.25, 43.54
    ring = [[x, y], [x + 0.0001, y], [x + 0.0001, y + 0.0001], [x, y]]
    coords = [ring] if geom_type == "Polygon" else [[ring]]
    return {
        "type": "Feature",
        "geometry": {"type": geom_type, "coordinates": coords},
        "properties": {"BLDID": oid, "SOURCE": "PLAN", "Shape__Area": 80.4},
    }


@pytest.fixture
def paths(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "SLIM_PATH", str(tmp_path / "slim.geojsonl"))
    monkeypatch.setattr(config, "COUNT_PATH", str(tmp_path / "count"))
    monkeypatch.setattr(slim_mod, "MIN_EXPECTED", 2)
    monkeypatch.setattr(slim_mod, "MAX_EXPECTED", 10)
    return tmp_path


def _write_source(path, features):
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}))


def test_slim_writes_one_line_per_polygon_and_skips_the_rest(paths):
    src = paths / "src.geojson"
    point = {"type": "Feature", "geometry": {"type": "Point", "coordinates": [0, 0]},
             "properties": {}}
    _write_source(src, [_feature(1), _feature(2, "MultiPolygon"), point,
                        {"type": "Feature", "geometry": None, "properties": {}}])
    slim(str(src))
    lines = [json.loads(l) for l in open(config.SLIM_PATH, encoding="utf-8")]
    assert [l["properties"]["bldid"] for l in lines] == [1, 2]
    assert lines[1]["geometry"]["type"] == "MultiPolygon"
    assert lines[0]["properties"] == {"bldid": 1, "source": "PLAN", "area": 80}
    assert open(config.COUNT_PATH).read() == "2"


def test_an_implausible_count_aborts(paths):
    src = paths / "src.geojson"
    _write_source(src, [_feature(1)])
    with pytest.raises(RuntimeError, match="outside the expected range"):
        slim(str(src))
