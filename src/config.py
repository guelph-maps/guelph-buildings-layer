"""Configuration constants for the Guelph buildings tile layer build.

Single source of truth. No logic here.

Sibling of guelph-parks-layer, and cloned from it: the same pipeline
(download -> slim -> compare -> vector + raster -> site -> publish), pointed at
the City of Guelph Buildings layer instead of its Park Boundary. What changes
is scale -- ~39,000 polygons instead of 126 -- and that a building carries no
name, so the raster draws outlines only and the gap page lists buildings by
size rather than by name.
"""

import os

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_DIR, "data")
BUILD_DIR = os.path.join(PROJECT_DIR, "build")
SITE_DIR = os.path.join(BUILD_DIR, "site")
ASSETS_DIR = os.path.join(PROJECT_DIR, "assets")
LOGS_DIR = os.path.join(PROJECT_DIR, "logs")

MBTILES_PATH = os.path.join(BUILD_DIR, "buildings.mbtiles")
SLIM_PATH = os.path.join(DATA_DIR, "buildings-slim.geojsonl")
COUNT_PATH = os.path.join(DATA_DIR, "buildings.count")
LAST_DOWNLOAD_PATH = os.path.join(DATA_DIR, ".last-download.json")

VECTOR_TILE_DIR = os.path.join(SITE_DIR, "tiles", "vector")
RASTER_TILE_DIR = os.path.join(SITE_DIR, "tiles", "raster")

# Data source: City of Guelph Buildings (OpenData1 layer 10), ~38,900
# polygons, ~28 MB as GeoJSON. maxRecordCount is 100,000, so one query is the
# whole layer. The service stores geometry in EPSG:26917, so outSR=4326 is not
# optional -- without it every downstream lon/lat is UTM metres.
FEATURE_SERVER = (
    "https://gismaps.guelph.ca/hosting/rest/services/OpenData/OpenData1"
    "/FeatureServer/10"
)
DATASET_URL = (
    f"{FEATURE_SERVER}/query?where=1%3D1&outFields=*&outSR=4326&f=geojson"
)
# The catalogue entry on explore.guelph.ca has no stable item page for this
# layer either, so the FeatureServer URL is what a reader is pointed at.
DATASET_PAGE = FEATURE_SERVER
# This layer REDISTRIBUTES City data as published tiles, and the licence
# attaches a required attribution to that. It is carried on the landing page
# and the gap page. See the README section "Licence"; it is a condition, not a
# courtesy.
LICENSE_URL = "https://gismaps.guelph.ca/Images/OpenDataLicenceVersion2.pdf"
LICENSE_NOTICE = (
    "Contains information licensed under the Open Government Licence "
    "– City of Guelph."
)
# Plain-ASCII attribution embedded in tile metadata (it is passed through a
# shell, where the en dash in LICENSE_NOTICE is not safe).
ATTRIBUTION = (
    "Contains information licensed under the Open Government Licence "
    "- City of Guelph"
)

# GitHub Pages target. PAGES_URL carries NO trailing slash: every tile URL on
# the site is built as f"{PAGES_URL}/tiles/...", and that string is the one
# thing on the page a reader copies verbatim into their editor.
GITHUB_REPO = "guelph-maps/guelph-buildings-layer"
PAGES_URL = "https://guelph-maps.github.io/guelph-buildings-layer"

# WSL distro that has tippecanoe installed (see wsl-setup.md). Used on Windows
# only; elsewhere tippecanoe is run directly.
WSL_DISTRO = "Ubuntu"

# Vector tiles. iD requests tiles at (map zoom - 1) and does NOT overzoom, so
# tiles must be generated natively through the zooms used for mapping.
# Buildings are only worth drawing once a mapper is zoomed in to edit them;
# z14 is the overview floor (the parks layer starts at z10).
VECTOR_MINZOOM = 14
VECTOR_MAXZOOM = 19
VECTOR_LAYER_NAME = "buildings"

# Raster tiles. Editors overzoom the top zoom further. One zoom deeper than the
# parks layer: a house outline at z17 is a dozen pixels across, too coarse to
# trace a corner against.
RASTER_ZOOMS = [15, 16, 17, 18]

# Source property keys read from the Buildings GeoJSON.
BLDID_KEY = "BLDID"          # the City's building id; 45 rows carry none
SOURCE_KEY = "SOURCE"        # how the outline was captured -- see below
AREA_KEY = "Shape__Area"     # square metres (computed in the UTM source CRS)
NAME_KEY = "NAME"            # four rows ("Metalworks Phase 1".."4"), else null

# SOURCE says how each outline was captured. Measured 2026-10-08 on 38,944
# rows: "Aerial photography" 38,620 (+1 spelled "Aerial photgraphy"), "PLAN"
# 317, "ORTHO" 3, "ORTHOPHOTO" 1, "CAD" 1, "ARDU MEMO" 1. The PLAN rows were
# drawn from a submitted site plan, not traced from imagery: the building may
# not be built yet, or not built as drawn. They are kept, drawn in a
# different colour, and listed as their own gap category.
PLAN_SOURCES = frozenset({"plan"})

# A City building with no OSM building on it, and smaller than this, is a
# shed or a garage more often than not. The City captures down to ~5 m^2
# (933 rows under 30 m^2), and OSM mappers routinely skip outbuildings, so
# these get their own category, off by default on the gap page, rather than
# burying the houses and plazas OSM is actually missing.
SMALL_AREA_M2 = 30

# --- OSM comparison (gap-review page) ---
# Buildings are pulled from OSM via Overpass and matched against the City
# polygons by spatial overlap; the gaps feed build/site/gaps/.
#
# The mirror list is the parks layer's, for the parks layer's reasons:
# overpass.kumi.systems and overpass.private.coffee have both been caught
# serving months-stale data, which looks exactly like success.
# OSM_MAX_AGE_DAYS refuses such a reply from any mirror.
OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
)
OVERPASS_TIMEOUT = 600
OVERPASS_ROUNDS = 3
OVERPASS_ROUND_WAIT = 60
# Floor on a reply's element count. A regional instance answers an
# out-of-region bbox with a valid EMPTY result, and taking that at face value
# reports every City building as missing from OSM. About half the first live
# reply: 49,695 elements from overpass-api.de on 2026-10-09.
OSM_MIN_ELEMENTS = 25000
OSM_MAX_AGE_DAYS = 3
# Overpass rejects the default requests User-Agent (HTTP 406); identify the tool.
USER_AGENT = "guelph-buildings-layer/0.1 (toronto@comentality.com)"
# Guelph bounding box (S, W, N, E), verbatim from guelph-beholder's config.toml
# -- a touch larger than the city. OSM buildings outside the city simply match
# nothing, so a loose box is harmless.
GUELPH_BBOX = (43.46, -80.34, 43.60, -80.14)
# Guelph city centre; where the preview and gap maps open.
GUELPH_CENTER = (43.5448, -80.2482)
OSM_CACHE_PATH = os.path.join(DATA_DIR, "osm-buildings.json")
# When the cached Overpass reply was fetched, from where, and the OSM database
# timestamp the reply declares about itself.
OSM_FETCH_PATH = os.path.join(DATA_DIR, ".osm-fetch.json")
GAPS_GEOJSON_PATH = os.path.join(DATA_DIR, "gaps.geojson")
GAPS_COUNT_PATH = os.path.join(DATA_DIR, "gaps.count.json")

# --- Gap history (trend page) ---
# One JSON line per live compare run. It lives in data/ like the rest of the
# observer's state; its published copy re-seeds a checkout that has none.
HISTORY_PATH = os.path.join(DATA_DIR, "history.jsonl")
HISTORY_URL = f"{PAGES_URL}/gaps/history.jsonl"
