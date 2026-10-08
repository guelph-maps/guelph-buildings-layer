"""Render building polygons into raster (PNG) map tiles using Pillow.

Pure Python -- no native dependencies, runs the same on Windows and Linux.

Much smaller than the parks layer's renderer: a building has no name, so there
is no label placement and no per-feature colour. Each polygon is a translucent
fill under a solid outline, in one of two colours -- violet for an outline the
City traced from imagery, orange for one it drew from a site plan (which may
not be built yet; see config.PLAN_SOURCES). Violet reads over both the OSM
carto basemap and aerial imagery, and is not the salmon iD draws OSM
buildings in, so the two sets of outlines stay distinguishable where they
disagree.
"""

import json
import os
from collections import defaultdict

from PIL import Image, ImageDraw

from src import config
from src.slim import is_plan
from src.tilemath import TILE_SIZE, lonlat_to_pixel

IMAGERY_OUTLINE = (95, 61, 196, 255)    # #5f3dc4
PLAN_OUTLINE = (232, 89, 12, 255)       # #e8590c, the gap page's "plan" colour
FILL_ALPHA = 56
CLEAR = (0, 0, 0, 0)

# Outline width by zoom: one pixel while a house is a dozen pixels across,
# two once it is big enough that a hairline gets lost against roof texture.
WIDE_OUTLINE_MIN_ZOOM = 17


def build_raster(slim_path=None):
    """Render PNG tiles for every zoom in config.RASTER_ZOOMS.

    Returns a dict {zoom: tile_count}.
    """
    slim_path = slim_path or config.SLIM_PATH
    features = _read_features(slim_path)
    return {z: _render_zoom(features, z) for z in config.RASTER_ZOOMS}


def _read_features(slim_path):
    """Return [(outline_rgba, [rings_lonlat, ...]), ...]: one entry per polygon."""
    features = []
    with open(slim_path, encoding="utf-8") as f:
        for line in f:
            feat = json.loads(line)
            geom = feat["geometry"]
            colour = (PLAN_OUTLINE if is_plan(feat["properties"].get("source"))
                      else IMAGERY_OUTLINE)
            polys = (geom["coordinates"] if geom["type"] == "MultiPolygon"
                     else [geom["coordinates"]])
            for rings in polys:
                features.append((colour, rings))
    return features


def _render_zoom(features, zoom):
    print(f"Raster z{zoom}: bucketing {len(features):,} polygons into tiles ...")
    width = 2 if zoom >= WIDE_OUTLINE_MIN_ZOOM else 1
    tiles = defaultdict(list)
    for colour, rings in features:
        projected = [[lonlat_to_pixel(lon, lat, zoom) for lon, lat in ring]
                     for ring in rings]
        xs = [p[0] for p in projected[0]]
        ys = [p[1] for p in projected[0]]
        for key in _tiles_touching((min(xs), min(ys), max(xs), max(ys)), width):
            tiles[key].append((colour, projected[0], projected[1:]))

    out_dir = os.path.join(config.RASTER_TILE_DIR, str(zoom))
    print(f"Raster z{zoom}: rendering {len(tiles):,} tiles ...")
    made_dirs = set()
    written = 0
    for (tx, ty), polys in tiles.items():
        img = _render_tile(tx, ty, polys, width)
        if img.getbbox() is None:
            continue  # bbox over-approximation: polygon never entered this tile
        tdir = os.path.join(out_dir, str(tx))
        if tdir not in made_dirs:
            os.makedirs(tdir, exist_ok=True)
            made_dirs.add(tdir)
        img.save(os.path.join(tdir, f"{ty}.png"), optimize=True)
        written += 1
    return written


def _tiles_touching(bbox, pad):
    x0, y0, x1, y1 = bbox
    for tx in range(int((x0 - pad) // TILE_SIZE), int((x1 + pad) // TILE_SIZE) + 1):
        for ty in range(int((y0 - pad) // TILE_SIZE), int((y1 + pad) // TILE_SIZE) + 1):
            yield (tx, ty)


def _render_tile(tx, ty, polys, width):
    img = Image.new("RGBA", (TILE_SIZE, TILE_SIZE), CLEAR)
    draw = ImageDraw.Draw(img)
    ox, oy = tx * TILE_SIZE, ty * TILE_SIZE

    def local(ring):
        return [(x - ox, y - oy) for x, y in ring]

    # ImageDraw writes pixels rather than blending them, so a fill is laid
    # once however many polygons overlap, and a hole can be cut by drawing it
    # clear. Polygons with holes go first, so cutting a courtyard never erases
    # a separate building standing inside it.
    for colour, ext, holes in sorted(polys, key=lambda p: not p[2]):
        draw.polygon(local(ext), fill=colour[:3] + (FILL_ALPHA,))
        for hole in holes:
            draw.polygon(local(hole), fill=CLEAR)
    for colour, ext, holes in polys:
        for ring in (ext, *holes):
            pts = local(ring)
            draw.line(pts + pts[:1], fill=colour, width=width)
    return img
