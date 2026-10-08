"""Unit tests for matching City buildings against OSM buildings.

The parks layer matches 126 polygons by scanning every OSM area; at ~39,000
buildings this one goes through a grid index, and the tests below pin what
that index and the overlap test must not get wrong: an overlap that crosses a
grid cell, the L-shaped building whose centroid sits outside both outlines,
and the category an unmatched building lands in.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import compare, config  # noqa: E402

# Downtown Guelph; one metre is ~0.0000124 deg of longitude, ~0.000009 of latitude.
X0, Y0 = -80.2482, 43.5448
MX, MY = 0.0000124, 0.000009


def _rect(x, y, w, h):
    """A w x h metre rectangle with its south-west corner x, y metres from X0, Y0."""
    x0, y0 = X0 + x * MX, Y0 + y * MY
    x1, y1 = x0 + w * MX, y0 + h * MY
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]


def _l_shape(x, y):
    """A 30 x 30 m L, arms 6 m thick: its centroid is outside the L itself."""
    pts = [(0, 0), (30, 0), (30, 6), (6, 6), (6, 30), (0, 30), (0, 0)]
    return [(X0 + (x + px) * MX, Y0 + (y + py) * MY) for px, py in pts]


def _city(ring, **props):
    geom = {"type": "Polygon", "coordinates": [[list(p) for p in ring]]}
    return {
        "props": {"area": 100, "source": "Aerial photography", **props},
        "geom": geom,
        "outers": [ring],
        "bbox": compare._bbox(ring),
        "centroid": compare._centroid(ring),
    }


def _osm(ring, oid=1):
    return compare._make_ring([{"lon": x, "lat": y} for x, y in ring], "way", oid)


def test_the_same_building_traced_twice_matches():
    city = _city(_rect(0, 0, 12, 9))
    osm = _osm(_rect(0.8, -0.6, 12, 9))       # off by under a metre
    gaps, counts = compare._match([city], [osm])
    assert gaps == [] and counts["missing"] == 0


def test_a_building_with_nothing_on_it_is_missing():
    city = _city(_rect(0, 0, 12, 9))
    osm = _osm(_rect(40, 0, 12, 9))           # the neighbour, not this house
    gaps, counts = compare._match([city], [osm])
    assert counts == {"missing": 1, "small": 0, "plan": 0}
    assert gaps[0]["properties"]["status"] == "missing"
    assert gaps[0]["properties"]["source"] == "Aerial photography"


def test_an_l_shape_matches_although_its_centroid_is_outside_both():
    # Neither centroid test can see this pair: the L's centroid is in its own
    # notch, outside both outlines. The pulled-in corners are what catch it.
    city_ring = _l_shape(0, 0)
    osm_ring = _l_shape(0.5, 0.5)
    city = _city(city_ring)
    assert not compare._point_in_ring(city["centroid"], city_ring)
    assert not compare._point_in_ring(compare._centroid(osm_ring), city_ring)
    gaps, _counts = compare._match([city], [_osm(osm_ring)])
    assert gaps == []


def test_a_match_across_a_grid_cell_boundary_is_found():
    # The City building sits wholly east of a cell boundary; the OSM outline
    # of the same building (drawn with its neighbour) starts west of it. An
    # index that filed the OSM ring under its south-west cell only would never
    # offer it to this building.
    boundary = (X0 // compare._CELL) * compare._CELL
    east = (boundary - X0) / MX                       # boundary, in metres
    city = _city(_rect(east + 1, 0, 12, 9))
    osm = _osm(_rect(east - 20, 0, 33, 9))
    assert compare._cells(city["bbox"]).__next__() != \
        compare._cells(osm["bbox"]).__next__()
    gaps, _counts = compare._match([city], [osm])
    assert gaps == []


def test_small_and_plan_buildings_get_their_own_categories():
    shed = _city(_rect(0, 0, 3, 4), area=12)
    planned = _city(_rect(50, 0, 30, 20), area=600, source="PLAN")
    planned_shed = _city(_rect(100, 0, 3, 4), area=12, source="PLAN")
    house = _city(_rect(150, 0, 12, 9), area=108)
    gaps, counts = compare._match([shed, planned, planned_shed, house], [])
    assert counts == {"missing": 1, "small": 1, "plan": 2}
    assert [g["properties"]["status"] for g in gaps] == \
        ["small", "plan", "plan", "missing"]


def test_the_threshold_itself_is_not_small():
    at = _city(_rect(0, 0, 5, 6), area=config.SMALL_AREA_M2)
    under = _city(_rect(50, 0, 5, 6), area=config.SMALL_AREA_M2 - 1)
    gaps, _counts = compare._match([at, under], [])
    assert [g["properties"]["status"] for g in gaps] == ["missing", "small"]


def test_centroid_is_stable_at_lonlat_magnitudes():
    # Summed raw, the shoelace terms for a 10 m square at Guelph's lon/lat
    # cancel to noise; the translated sum must land in the middle.
    ring = _rect(0, 0, 10, 10)
    cx, cy = compare._centroid(ring)
    assert abs(cx - (X0 + 5 * MX)) < MX / 100
    assert abs(cy - (Y0 + 5 * MY)) < MY / 100
