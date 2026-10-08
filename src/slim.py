"""Reduce the Buildings GeoJSON to a slim newline-delimited GeoJSON.

The source is a ~28 MB FeatureCollection; it is parsed as a stream with ijson.
Every polygon is kept -- the layer has no status or class field to filter on,
and every row is a building -- and its properties are cut down to the four a
mapper can use:

  bldid   the City's building id (absent on 45 rows)
  source  how the outline was captured, as the City writes it
  area    footprint in square metres, rounded
  name    on the four rows that have one

The one file, data/buildings-slim.geojsonl, feeds the tile builders and the
gap tool alike.
"""

import json
import os

import ijson

from src import config

# Sanity bounds for the slimmed feature count (38,944 polygons on 2026-10-08).
MIN_EXPECTED = 35_000
MAX_EXPECTED = 45_000


def slim(src_path):
    """Stream the GeoJSON into data/buildings-slim.geojsonl.

    Returns the slim file path. Raises if the feature count is implausible.
    """
    print(f"Slimming {src_path} ...")
    os.makedirs(config.DATA_DIR, exist_ok=True)

    count = 0
    skipped = 0
    with open(src_path, "rb") as src, \
            open(config.SLIM_PATH, "w", encoding="utf-8") as out:
        for feature in ijson.items(src, "features.item"):
            geom = feature.get("geometry") or {}
            if geom.get("type") not in ("Polygon", "MultiPolygon") \
                    or not geom.get("coordinates"):
                skipped += 1
                continue
            out.write(json.dumps({
                "type": "Feature",
                "geometry": {
                    "type": geom["type"],
                    "coordinates": _plain(geom["coordinates"]),
                },
                "properties": slim_props(feature.get("properties") or {}),
            }) + "\n")
            count += 1
            if count % 10_000 == 0:
                print(f"  {count:,} features ...")

    with open(config.COUNT_PATH, "w", encoding="utf-8") as f:
        f.write(str(count))

    print(f"Done: {config.SLIM_PATH} ({count:,} features, {skipped:,} skipped)")
    if not MIN_EXPECTED <= count <= MAX_EXPECTED:
        raise RuntimeError(
            f"Slim feature count {count:,} is outside the expected range "
            f"{MIN_EXPECTED:,}-{MAX_EXPECTED:,} -- aborting."
        )
    return config.SLIM_PATH


def slim_props(props_in):
    """The kept properties of one City building."""
    props = {}
    bldid = props_in.get(config.BLDID_KEY)
    if bldid is not None:
        props["bldid"] = int(bldid)
    source = props_in.get(config.SOURCE_KEY)
    if source and str(source).strip():
        props["source"] = str(source).strip()
    area = props_in.get(config.AREA_KEY)
    if area is not None:
        props["area"] = int(round(float(area)))
    name = props_in.get(config.NAME_KEY)
    if name and str(name).strip():
        props["name"] = str(name).strip()
    return props


def is_plan(source):
    """An outline drawn from a site plan rather than traced from imagery."""
    return bool(source) and str(source).strip().lower() in config.PLAN_SOURCES


def _plain(coords):
    """Recursively convert ijson Decimals to floats for compact json output."""
    if isinstance(coords, list):
        return [_plain(c) for c in coords]
    return float(coords)
