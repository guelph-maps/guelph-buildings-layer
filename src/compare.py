"""Compare the City building outlines against OSM buildings.

Pulls every building from OpenStreetMap (Overpass) within Guelph, then for
each City polygon checks whether an OSM building overlaps it. The City
buildings that nothing in OSM overlaps are written to data/gaps.geojson, in
one of three categories:

  * "missing" -- a building OSM does not have (add it);
  * "small"   -- the same, under config.SMALL_AREA_M2: a shed or a garage more
                 often than not, kept apart so they do not bury the rest;
  * "plan"    -- the same, for an outline the City drew from a site plan
                 rather than from imagery: check it was built before adding it.

Overlap is tested in pure Python after a bounding-box prefilter on a grid
index -- enough for a review tool, no GIS dependency. Two polygons overlap
when either one's centroid falls inside the other, or when one of the City
polygon's corners, pulled a little toward its centre, falls inside the OSM
one; that last test catches the L- and U-shaped buildings whose centroids sit
outside both outlines. A flaky Overpass falls back to the cached response, but
only after every mirror has been tried several times -- see _load_osm.

The comparison runs one way only. An OSM building with no City building under
it is not reported: OSM holds outbuildings, demolitions and new builds the
City layer lags behind on, and telling those apart needs imagery, not a diff.
"""

import json
import time
from collections import defaultdict

import requests
from layerkit import overpass
# Raised by overpass.load_osm; callers and tests name it as compare's.
from layerkit.overpass import OsmUnavailable  # noqa: F401

from src import config, history
from src.slim import is_plan

STATUSES = ("missing", "small", "plan")

# Grid cell for the OSM bbox index, in degrees: ~200 m at Guelph's latitude,
# a few dozen buildings per cell in the dense core.
_CELL = 0.002
# How far each City corner is pulled toward its ring's centroid before it is
# tested against an OSM outline. Two tracings of the same wall disagree by a
# metre or so; at 25% a 10 m house corner moves ~2.5 m inside its own walls.
_CORNER_PULL = 0.25


def compare():
    """Build data/gaps.geojson + summary from City vs OSM. Returns the summary."""
    data, osm_date, from_cache = _load_osm()
    rings = _osm_rings(data)
    print(f"OSM building rings: {len(rings):,}")
    city = list(_city_features())
    print(f"City buildings:     {len(city):,}")

    gaps, counts = _match(city, rings)
    _write_gaps(gaps)

    summary = {"osm_rings": len(rings), "city": len(city),
               "osm_date": osm_date, "osm_stale": from_cache, **counts}
    with open(config.GAPS_COUNT_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(
        f"Gaps: {counts['missing']:,} missing, {counts['small']:,} small, "
        f"{counts['plan']:,} from site plans"
    )
    if from_cache:
        print(f"NOTE: compared against cached OSM data from {osm_date}, "
              f"not a live Overpass fetch.")
    history.record(summary)
    return summary


# --- OSM source -------------------------------------------------------------

def _overpass_query():
    """The Overpass QL for every building in the Guelph bbox."""
    s, w, n, e = config.GUELPH_BBOX
    bbox = f"{s},{w},{n},{e}"
    # building=no is a mapper saying "this is not a building" -- a roof over a
    # fuel pump, a carport -- so it cannot stand in for a City building.
    # "out geom" (body verbosity) so RELATIONS carry their members + geometry;
    # "out tags geom" would strip member lists and silently drop every relation.
    return (
        f"[out:json][timeout:{config.OVERPASS_TIMEOUT - 60}];\n(\n"
        f'  way["building"]["building"!="no"]({bbox});\n'
        f'  relation["building"]["building"!="no"]({bbox});\n'
        ");\nout geom;"
    )


def _load_osm():
    """Return (data, osm_date, from_cache) for OSM buildings.

    The fetch -- every mirror, the list retried, then the cache -- is
    layerkit.overpass.load_osm; the reasons for each rule are written there.
    """
    return overpass.load_osm(
        _overpass_query(), what="buildings",
        urls=config.OVERPASS_URLS, rounds=config.OVERPASS_ROUNDS,
        round_wait=config.OVERPASS_ROUND_WAIT,
        cache_path=config.OSM_CACHE_PATH, fetch_path=config.OSM_FETCH_PATH,
        try_one=_try_overpass, undated=None)


def _try_overpass(url, query):
    """One attempt at one mirror; None if it failed or answered implausibly."""
    return overpass.try_overpass(
        url, query, user_agent=config.USER_AGENT,
        timeout=config.OVERPASS_TIMEOUT,
        min_elements=config.OSM_MIN_ELEMENTS,
        max_age_days=config.OSM_MAX_AGE_DAYS)


def _load_cache():
    """(data, osm_date) for the cached Overpass reply, or None."""
    return overpass.load_cache(config.OSM_CACHE_PATH, config.OSM_FETCH_PATH)


def _osm_base(data):
    """How current the OSM half of the diff is: the reply's own
    osm3s.timestamp_osm_base, trimmed to the minute for display."""
    return overpass.osm_base(data, undated=None)


def _osm_base_time(data):
    """The same timestamp as an aware datetime, or None if absent or garbled."""
    return overpass.osm_base_time(data)


def _cache_date():
    """How current the cached reply is: the sidecar, else the file's mtime."""
    return overpass.cache_date(config.OSM_CACHE_PATH, config.OSM_FETCH_PATH)


def _save_fetch(fetched, url, osm_base, data):
    overpass.save_fetch(config.OSM_FETCH_PATH, fetched, url, osm_base, data)




def _osm_rings(data):
    """Flatten OSM ways and relation outer members into matchable rings."""
    rings = []
    for el in data.get("elements", []):
        if el.get("type") == "way":
            rings.append(_make_ring(el.get("geometry"), "way", el["id"]))
        elif el.get("type") == "relation":
            for loop in _relation_outer_loops(el):
                rings.append(_make_ring(loop, "relation", el["id"]))
    return [r for r in rings if r]


def _relation_outer_loops(rel):
    """Stitch a multipolygon relation's outer member ways into closed loops.

    OSM splits a long outer boundary across several ways; only joined
    end-to-end do they form the ring(s). Without this, each open segment looks
    like a degenerate sliver. Returns a list of point lists (geometry dicts),
    one per assembled loop.
    """
    segs = [m["geometry"] for m in rel.get("members", [])
            if m.get("type") == "way" and m.get("role") in ("outer", "")
            and m.get("geometry")]
    loops = []
    used = [False] * len(segs)
    for i in range(len(segs)):
        if used[i]:
            continue
        used[i] = True
        loop = list(segs[i])
        grew = True
        while grew and _pt(loop[0]) != _pt(loop[-1]):
            grew = False
            for j, other in enumerate(segs):
                if used[j]:
                    continue
                if _pt(other[0]) == _pt(loop[-1]):
                    loop.extend(other[1:])
                elif _pt(other[-1]) == _pt(loop[-1]):
                    loop.extend(reversed(other[:-1]))
                elif _pt(other[-1]) == _pt(loop[0]):
                    loop[:0] = other[:-1]
                elif _pt(other[0]) == _pt(loop[0]):
                    loop[:0] = list(reversed(other[1:]))
                else:
                    continue
                used[j] = grew = True
        loops.append(loop)
    return loops


def _pt(p):
    return (p["lat"], p["lon"])




def _make_ring(geom, otype, oid):
    if not geom:
        return None
    pts = [(p["lon"], p["lat"]) for p in geom if "lon" in p and "lat" in p]
    if len(pts) < 3:
        return None
    return {
        "pts": pts,
        "otype": otype,
        "oid": oid,
        "bbox": _bbox(pts),
        "centroid": _centroid(pts),
    }


# --- City source ------------------------------------------------------------

def _city_features():
    with open(config.SLIM_PATH, encoding="utf-8") as f:
        for line in f:
            feat = json.loads(line)
            outers = _outer_rings(feat["geometry"])
            if not outers:
                continue
            allpts = [p for ring in outers for p in ring]
            yield {
                "props": feat.get("properties") or {},
                "geom": feat["geometry"],
                "outers": outers,
                "bbox": _bbox(allpts),
                "centroid": _centroid(max(outers, key=_ring_area)),
            }


def _outer_rings(geom):
    """Outer ring(s) as lists of (lon, lat). Polygon -> 1, MultiPolygon -> many."""
    coords = geom.get("coordinates")
    if not coords:
        return []
    if geom["type"] == "Polygon":
        return [[tuple(p) for p in coords[0]]]
    if geom["type"] == "MultiPolygon":
        return [[tuple(p) for p in poly[0]] for poly in coords if poly]
    return []


# --- Matching ---------------------------------------------------------------

def _match(city, rings):
    index = _index(rings)
    gaps = []
    counts = {s: 0 for s in STATUSES}
    for c in city:
        if _find_match(c, index) is not None:
            continue
        status = _status(c["props"])
        gaps.append(_gap_feature(c, status))
        counts[status] += 1
    return gaps, counts


def _status(props):
    """Which gap category an unmatched City building falls in."""
    if is_plan(props.get("source")):
        return "plan"
    if props.get("area", 0) < config.SMALL_AREA_M2:
        return "small"
    return "missing"


def _index(rings):
    """Grid cell -> OSM rings whose bbox touches it."""
    index = defaultdict(list)
    for r in rings:
        for key in _cells(r["bbox"]):
            index[key].append(r)
    return index


def _cells(bbox):
    x0, y0, x1, y1 = bbox
    for cx in range(int(x0 // _CELL), int(x1 // _CELL) + 1):
        for cy in range(int(y0 // _CELL), int(y1 // _CELL) + 1):
            yield (cx, cy)


def _find_match(c, index):
    """An OSM ring overlapping the City polygon, or None."""
    seen = set()
    probes = None
    for key in _cells(c["bbox"]):
        for r in index.get(key, ()):
            if id(r) in seen or not _bbox_overlap(c["bbox"], r["bbox"]):
                continue
            seen.add(id(r))
            if _point_in_ring(c["centroid"], r["pts"]) or any(
                _point_in_ring(r["centroid"], outer) for outer in c["outers"]
            ):
                return r
            if probes is None:
                probes = _corner_probes(c["outers"])
            if any(_point_in_ring(p, r["pts"]) for p in probes):
                return r
    return None


def _corner_probes(outers):
    """Each corner of each outer ring, pulled _CORNER_PULL toward its centroid."""
    probes = []
    for ring in outers:
        cx, cy = _centroid(ring)
        for x, y in ring:
            probes.append((x + (cx - x) * _CORNER_PULL,
                           y + (cy - y) * _CORNER_PULL))
    return probes


def _gap_feature(c, status):
    return {
        "type": "Feature",
        "properties": {**c["props"], "status": status},
        "geometry": _round_geom(c["geom"]),
    }


def _write_gaps(gaps):
    with open(config.GAPS_GEOJSON_PATH, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": gaps}, f)


# --- Geometry helpers -------------------------------------------------------

def _bbox(pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def _bbox_overlap(a, b):
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def _centroid(pts):
    """Area-weighted polygon centroid (shoelace); mean for degenerate rings.

    Translated to the first vertex before summing: at lon/lat a building's
    cross-products are differences of numbers near 3,500, and summed raw they
    lose the centroid to float cancellation.
    """
    n = len(pts)
    ox, oy = pts[0]
    area = cx = cy = 0.0
    for i in range(n):
        x0, y0 = pts[i][0] - ox, pts[i][1] - oy
        x1, y1 = pts[(i + 1) % n][0] - ox, pts[(i + 1) % n][1] - oy
        cross = x0 * y1 - x1 * y0
        area += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    if area == 0:
        return (sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n)
    area *= 0.5
    return (cx / (6 * area) + ox, cy / (6 * area) + oy)


def _ring_area(pts):
    n = len(pts)
    ox, oy = pts[0]
    area = 0.0
    for i in range(n):
        x0, y0 = pts[i][0] - ox, pts[i][1] - oy
        x1, y1 = pts[(i + 1) % n][0] - ox, pts[(i + 1) % n][1] - oy
        area += x0 * y1 - x1 * y0
    return abs(area) / 2


def _point_in_ring(pt, pts):
    """Ray-casting point-in-polygon test."""
    x, y = pt
    n = len(pts)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if (yi > y) != (yj > y):
            xint = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < xint:
                inside = not inside
        j = i
    return inside


def _round_geom(geom):
    return {"type": geom["type"], "coordinates": _round(geom["coordinates"])}


def _round(c):
    if isinstance(c, (int, float)):
        return round(c, 6)  # ~0.1 m -- a building corner, not a park edge
    return [_round(x) for x in c]
