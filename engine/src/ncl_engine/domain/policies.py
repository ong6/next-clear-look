"""Public algorithm versions, limits, and honesty labels."""

SWATH_WIDTH_KM = 290.0
SWATH_HALF_WIDTH_M = 145_000.0
COARSE_STEP_SECONDS = 20
CROSSING_TOLERANCE_SECONDS = 0.05
MAX_AOI_VERTICES = 10_000
MAX_AOI_AREA_KM2 = 250_000.0
MAX_RASTER_PIXELS = 1_500_000
ARCHIVE_DAYS = 30

ORBIT_ALGORITHM = "sgp4-swath-v1"
SCL_ALGORITHM = "scl-aoi-v1"
THUMBNAIL_ALGORITHM = "aoi-thumbnail-v1"
LIKELIHOOD_ALGORITHM = "seasonal-beta-acquisition-clear-v1"

OPPORTUNITY_CAVEAT = "Geometric opportunity only; acquisition is not guaranteed."
LIKELIHOOD_INTERPRETATION = (
    "Historical likelihood of at least one acquired, AOI-clear look; "
    "not a weather forecast or acquisition promise."
)
