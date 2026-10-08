"""Tests for the raster tile renderer."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.raster import (  # noqa: E402
    CLEAR, FILL_ALPHA, IMAGERY_OUTLINE, PLAN_OUTLINE, _render_tile,
    _tiles_touching,
)


def _square(x0, y0, size):
    return [(x0, y0), (x0 + size, y0), (x0 + size, y0 + size), (x0, y0 + size)]


def test_fill_outline_and_hole():
    # A 200 px courtyard building in tile (0, 0), with a 60 px hole.
    ext, hole = _square(20, 20, 200), _square(90, 90, 60)
    img = _render_tile(0, 0, [(IMAGERY_OUTLINE, ext, [hole])], 1)
    assert img.getpixel((50, 50)) == IMAGERY_OUTLINE[:3] + (FILL_ALPHA,)
    assert img.getpixel((120, 120)) == CLEAR          # the courtyard
    assert img.getpixel((20, 100)) == IMAGERY_OUTLINE  # the west wall
    assert img.getpixel((5, 5)) == CLEAR


def test_a_hole_never_erases_a_building_standing_in_it():
    courtyard = (IMAGERY_OUTLINE, _square(20, 20, 200), [_square(70, 70, 100)])
    pavilion = (PLAN_OUTLINE, _square(100, 100, 40), [])
    # Whatever order the bucket hands them over in.
    for polys in ([pavilion, courtyard], [courtyard, pavilion]):
        img = _render_tile(0, 0, polys, 1)
        assert img.getpixel((120, 120)) == PLAN_OUTLINE[:3] + (FILL_ALPHA,)


def test_tile_coordinates_are_local():
    # The same square one tile east and south renders identically.
    a = _render_tile(0, 0, [(IMAGERY_OUTLINE, _square(10, 10, 50), [])], 2)
    b = _render_tile(1, 1, [(IMAGERY_OUTLINE, _square(266, 266, 50), [])], 2)
    assert a.tobytes() == b.tobytes()


def test_tiles_touching_includes_the_outline_overhang():
    # A polygon ending exactly on a tile edge still paints its outline there.
    assert set(_tiles_touching((10, 10, 256, 100), 1)) == {(0, 0), (1, 0)}
    assert set(_tiles_touching((10, 10, 200, 100), 1)) == {(0, 0)}
