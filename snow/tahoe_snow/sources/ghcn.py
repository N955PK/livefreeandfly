"""Hand-measured daily snowfall and liquid from GHCN-Daily (COOP and CoCoRaHS; no key).

A daily value on date D covers the 24 hours ending at the observation time on D
(local time). The observation time comes from the record when present.
"""
import io

import pandas as pd

from tahoe_snow.cache import get_text
from tahoe_snow.config import USER_AGENT  # noqa: F401  (documents the shared session identity)

DATA_URL = "https://www.ncei.noaa.gov/access/services/data/v1"
INVENTORY_URL = "https://www.ncei.noaa.gov/pub/data/ghcn/daily/ghcnd-inventory.txt"
STATIONS_URL = "https://www.ncei.noaa.gov/pub/data/ghcn/daily/ghcnd-stations.txt"
DEFAULT_OBS_HOUR = 7


def find_stations(bbox: tuple, min_elev_m: float, last_year_at_least: int,
                  needs: tuple = ("SNOW", "PRCP")) -> pd.DataFrame:
    """Stations inside ``bbox`` (lat0, lat1, lon0, lon1) reporting every element in ``needs``."""
    lat0, lat1, lon0, lon1 = bbox
    meta = {}
    for line in get_text("ghcn_meta", STATIONS_URL, max_age_h=24 * 30).splitlines():
        meta[line[:11]] = (float(line[31:37]), line[41:71].strip())
    spans = {}
    for line in get_text("ghcn_meta", INVENTORY_URL, max_age_h=24 * 30).splitlines():
        lat, lon, element = float(line[12:20]), float(line[21:30]), line[31:35]
        if lat0 < lat < lat1 and lon0 < lon < lon1 and element in needs:
            spans.setdefault(line[:11], {"lat": lat, "lon": lon})[element] = (int(line[36:40]), int(line[41:45]))
    rows = []
    for station, info in spans.items():
        if not all(element in info for element in needs):
            continue
        elev_m, name = meta[station]
        first = max(info[element][0] for element in needs)
        last = min(info[element][1] for element in needs)
        if elev_m >= min_elev_m and last >= last_year_at_least:
            rows.append({"station": station, "name": name, "lat": info["lat"], "lon": info["lon"],
                         "elev_m": elev_m, "first_year": first, "last_year": last})
    return pd.DataFrame(rows).sort_values("elev_m", ascending=False).reset_index(drop=True)


def _obs_hour(attributes: pd.Series) -> pd.Series:
    """Observation hour from the 'm,q,s,HHMM' attribute string; NaN when absent."""
    hhmm = attributes.fillna("").str.split(",").str[3].replace("", pd.NA)
    return pd.to_numeric(hhmm, errors="coerce") // 100


def _quality_ok(attributes: pd.Series) -> pd.Series:
    """True where the quality flag (second attribute field) is empty."""
    return attributes.fillna(",,").str.split(",").str[1].fillna("") == ""


def parse(csv_text: str) -> pd.DataFrame:
    raw = pd.read_csv(io.StringIO(csv_text), dtype=str)
    if raw.empty:
        return pd.DataFrame()
    out = pd.DataFrame(index=pd.to_datetime(raw["DATE"]))
    out.index.name = "date"
    names = {"SNOW": "snow_mm", "PRCP": "prcp_mm", "TMAX": "tmax_c", "TMIN": "tmin_c", "WESF": "wesf_mm",
             "SNWD": "depth_mm"}
    for element, column in names.items():
        if element not in raw:
            continue
        values = pd.to_numeric(raw[element], errors="coerce").to_numpy()
        attributes = raw.get(f"{element}_ATTRIBUTES", pd.Series([None] * len(raw)))
        ok = _quality_ok(attributes).to_numpy()
        out[column] = pd.Series(values, index=out.index).where(ok)
        if element in ("SNOW", "PRCP"):
            out[f"{column[:4]}_obs_hour"] = _obs_hour(attributes).to_numpy()
            # 'T' in the measurement flag marks a trace.
            out[f"{column[:4]}_trace"] = (attributes.fillna("").str.split(",").str[0] == "T").to_numpy()
    return out.sort_index()


def daily(station: str, start: str, end: str, max_age_h: float | None = None) -> pd.DataFrame:
    params = {"dataset": "daily-summaries", "stations": station, "dataTypes": "SNOW,PRCP,TMAX,TMIN,WESF,SNWD",
              "startDate": start, "endDate": end, "format": "csv", "units": "metric", "includeAttributes": "true"}
    return parse(get_text("ghcn", DATA_URL, params, max_age_h, suffix=".csv"))
