# ruff: noqa: N999
# Token required on all endpoints — include as ?token=... in the URL.
# Leave empty to disable auth (e.g. for local dev).
API_TOKEN = ""

# IANA timezone name — used for all display times
TIMEZONE = "Europe/Helsinki"

# City name for FMI weather API
FMI_CITY = "Helsinki"

# API key from https://portal-api.digitransit.fi
DIGITRANSIT_API_KEY = "your-key-here"

# Stop codes printed on the physical sign, also findable on https://www.hsl.fi/en
# lines is optional — omit to show all lines at the stop
from app.transport import StopConfig  # noqa: E402

HSL_STOPS = [
    StopConfig("H0062", lines={"561", "560", "54"}, walk_time_minutes=5),
    StopConfig("H2041"),
]
