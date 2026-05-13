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

# Secret iCal URL from Google Calendar settings — leave empty to disable
GCAL_ICAL_URL = ""

# Compass Group / Amica restaurant page URL — leave empty to disable
AMICA_URL = ""
AMICA_LABEL = ""

# Aromi (aromi.hel.fi) school lunch — leave empty to disable
# api_path: from the browser network inspector on the restaurant's Angular page
# restaurant_id and diner_group_id: GUIDs visible in the request URL / body
AROMI_URL = ""
AROMI_RESTAURANT_ID = ""
AROMI_DINER_GROUP_ID = ""
AROMI_LABEL = ""
