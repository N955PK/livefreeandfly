"""A weather station's latest hourly observations from the National Weather Service (api.weather.gov, no key).

Each observation carries its own UTC time. A value the station did not report in an hour is null there and may be
back the next hour, so each column is read on its own.
"""
import pandas as pd

from tahoe_snow.cache import get_json

URL = "https://api.weather.gov/stations/{station}/observations"
# Feed field -> column. Temperatures are in Celsius, speeds in km/h, directions in degrees the wind blows from.
FIELDS = {"temperature": "temp_c", "windSpeed": "wind_kmh", "windGust": "gust_kmh", "windDirection": "wind_from_deg"}


def parse(payload: dict) -> pd.DataFrame:
    """One row per observation, indexed by naive UTC time, oldest first."""
    rows = {}
    for feature in payload.get("features") or []:
        properties = feature.get("properties") or {}
        if not properties.get("timestamp"):
            continue
        stamp = pd.Timestamp(properties["timestamp"]).tz_convert("UTC").tz_localize(None)
        rows[stamp] = {column: (properties.get(field) or {}).get("value") for field, column in FIELDS.items()}
    out = pd.DataFrame.from_dict(rows, orient="index", columns=list(FIELDS.values()), dtype=float)
    out.index.name = "time_utc"
    return out.sort_index()


def observations(station: str, limit: int = 6, max_age_h: float | None = 1.0, timeout: float = 20,
                 retries: int = 2) -> pd.DataFrame:
    """The station's last ``limit`` observations."""
    return parse(get_json("nws", URL.format(station=station), {"limit": limit}, max_age_h, timeout=timeout,
                          retries=retries))
