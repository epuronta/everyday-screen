# ruff: noqa: N999
# Token required on all endpoints — include as ?token=... in the URL.
# Leave empty to disable auth (e.g. for local dev).
API_TOKEN = ""

# City name for FMI weather API
FMI_CITY = "Helsinki"

# API key from https://portal-api.digitransit.fi
DIGITRANSIT_API_KEY = "your-key-here"

# Stop codes printed on the physical sign, also findable on https://www.hsl.fi/en
HSL_STOPS = ["H0062", "H2041"]

# Optionally filter by line. Omit or set to None to show all lines at the stop.
HSL_LINES = {}
