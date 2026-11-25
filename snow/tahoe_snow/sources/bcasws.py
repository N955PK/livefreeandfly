"""Snow-sensor readings from British Columbia's Automated Snow Weather Stations (no key).

The province publishes one file per measure for the whole network: a row an hour since October 1, stamped in UTC,
and a column a station headed by its id and name ("2F10P Silver Star Mountain"). Snow water is in millimeters,
depth in centimeters and air temperature in Celsius. A station that lacks a sensor has no column in that file, or
an empty one. Frames carry the SNOTEL reader's column names, but their index is UTC, not a station clock.

The long record is in four more files beside them, an hour a row from October 2003 to the last September 30
(``SW_Archive.csv`` and its fellows, 40 to 85 MB each), with cumulative precipitation in millimeters among them.
``daily`` reads those as the SNOTEL reader's daily values, for fitting; nothing in a forecast build reads them.
"""
import io
from functools import lru_cache

import pandas as pd
import requests

from tahoe_snow.cache import get_json, get_text
from tahoe_snow.config import RAW, USER_AGENT, Station

URL = "https://www.env.gov.bc.ca/wsd/data_searches/snow/asws/data/{name}.csv"
FILES = {"SW": "swe_mm", "SD": "depth_cm", "TA": "tobs_c"}
# Readings outside these are sensor faults (a pillow reading far below zero, a depth spike).
VALID = {"swe_mm": (-25.0, 5000.0), "depth_cm": (-5.0, 1500.0), "tobs_c": (-50.0, 45.0), "prec_mm": (0.0, 20000.0)}
ARCHIVE = {"SW_Archive": "swe_mm", "SD_Archive": "depth_cm", "PC_Archive": "prec_mm", "TA_Archive": "tobs_c"}
# The province's list of its stations, with their positions and heights.
STATIONS_URL = "https://openmaps.gov.bc.ca/geo/pub/WHSE_WATER_MANAGEMENT.SSL_SNOW_ASWS_STNS_SP/ows"
STATIONS_QUERY = {"service": "WFS", "version": "2.0.0", "request": "GetFeature", "outputFormat": "json",
                  "typeName": "pub:WHSE_WATER_MANAGEMENT.SSL_SNOW_ASWS_STNS_SP", "srsName": "EPSG:4326"}
# SNOTEL's daily values are read at midnight Pacific standard time, which is this hour in UTC.
MIDNIGHT_PST_UTC_H = 8


def column(text: str, station_id: str) -> pd.Series:
    """One station's readings from a measure's file, or nothing where the file has no column for it."""
    table = pd.read_csv(io.StringIO(text), index_col=0, dtype=str)
    named = [name for name in table.columns if name.split(" ", 1)[0] == station_id]
    if not named:
        return pd.Series(dtype=float, index=pd.DatetimeIndex([]))
    series = pd.to_numeric(table[named[0]], errors="coerce")
    series.index = pd.to_datetime(table.index, errors="coerce")
    return series[series.index.notna()].dropna()


def parse(texts: dict, station_id: str) -> pd.DataFrame:
    """A station's hourly readings from the measures' files, ``{"SW": text, ...}``."""
    frames = {}
    for name, measure in FILES.items():
        series = column(texts[name], station_id) if name in texts else pd.Series(dtype=float)
        low, high = VALID[measure]
        frames[measure] = series.where(series.between(low, high))
    out = pd.DataFrame(frames).dropna(how="all").sort_index()
    out.index.name = "time_utc"
    return out


def hourly(station_id: str, start: str | None = None, end: str | None = None,
           max_age_h: float | None = None) -> pd.DataFrame:
    """Hourly readings since October 1, indexed by UTC. The dates are taken for the other readers' sake: the
    files hold the season whole."""
    texts = {name: get_text("bcasws", URL.format(name=name), None, max_age_h, suffix=".csv") for name in FILES}
    return parse(texts, station_id)


@lru_cache(maxsize=None)
def archive(name: str) -> pd.DataFrame:
    """One measure's long record: a row an hour in UTC, a column a station headed by its id alone. The parsed
    table is kept beside the file, which takes a minute to read."""
    folder = RAW / "bcasws_archive"
    kept, file = folder / f"{name}.parquet", folder / f"{name}.csv"
    if kept.exists():
        return pd.read_parquet(kept)
    if not file.exists():
        # Straight to disk: the cache's reader would guess at 80 MB of text's encoding first.
        folder.mkdir(parents=True, exist_ok=True)
        with requests.get(URL.format(name=name), headers={"User-Agent": USER_AGENT}, stream=True, timeout=300) as reply:
            reply.raise_for_status()
            with open(file, "wb") as out:
                for piece in reply.iter_content(1 << 20):
                    out.write(piece)
    table = pd.read_csv(file, index_col=0, low_memory=False)
    table.index = pd.to_datetime(table.index, errors="coerce")
    table = table[table.index.notna()].apply(pd.to_numeric, errors="coerce").astype("float32")
    table.columns = [column.split(" ", 1)[0] for column in table.columns]
    table = table.loc[:, ~table.columns.duplicated()].sort_index()
    table = table[~table.index.duplicated()]
    table.to_parquet(kept)
    return table


def daily_values(hourly: pd.DataFrame) -> pd.DataFrame:
    """Hourly readings in UTC as the SNOTEL reader's daily values: the value dated D is the reading at the end of
    D, Pacific standard time, and the day's temperatures are over those 24 hours. A cumulative reading is the
    median of the three hours about midnight, so one stray hour does not make a day's gain."""
    out = {}
    local = hourly.index - pd.Timedelta(hours=MIDNIGHT_PST_UTC_H)
    for column in ("swe_mm", "depth_cm", "prec_mm"):
        if column not in hourly:
            continue
        series = hourly[column].dropna()
        near = series[(series.index.hour >= MIDNIGHT_PST_UTC_H - 1) & (series.index.hour <= MIDNIGHT_PST_UTC_H + 1)]
        ends = (near.index - pd.Timedelta(hours=MIDNIGHT_PST_UTC_H - 1)).normalize()   # the day that begins there
        out[column] = near.groupby(ends - pd.Timedelta(days=1)).median()
    if "tobs_c" in hourly:
        by_day = hourly["tobs_c"].groupby(local.normalize())
        enough = by_day.count() >= 18
        out["tavg_c"], out["tmax_c"] = by_day.mean()[enough], by_day.max()[enough]
        out["tmin_c"] = by_day.min()[enough]
    frame = pd.DataFrame(out)
    frame.index.name = "date"
    return frame.sort_index()


def daily(station_id: str, start: str, end: str) -> pd.DataFrame:
    """A station's daily values from the long record and this season's files, on the SNOTEL reader's columns."""
    frames = {}
    for name, measure in ARCHIVE.items():
        table = archive(name)
        nothing = pd.Series(dtype=float, index=pd.DatetimeIndex([]))
        old = table[station_id] if station_id in table else nothing
        new = column(get_text("bcasws", URL.format(name=name.split("_")[0]), None, 24.0, suffix=".csv"), station_id)
        series = pd.concat([old.dropna().astype(float), new[new.index > table.index.max()]])
        low, high = VALID[measure]
        frames[measure] = series.where(series.between(low, high))
    hourly_all = pd.DataFrame(frames)
    hourly_all = hourly_all[(hourly_all.index >= pd.Timestamp(start))
                            & (hourly_all.index <= pd.Timestamp(end) + pd.Timedelta(days=2))]
    out = daily_values(hourly_all)
    return out[(out.index >= start) & (out.index <= end)]


def stations(bbox: tuple) -> dict:
    """Every active station of the province's list inside ``bbox`` (lat0, lat1, lon0, lon1)."""
    lat0, lat1, lon0, lon1 = bbox
    found = {}
    for feature in get_json("bcasws_meta", STATIONS_URL, STATIONS_QUERY, 24 * 30)["features"]:
        row = feature["properties"]
        if row["STATUS"] == "Active" and lat0 < row["LATITUDE"] < lat1 and lon0 < row["LONGITUDE"] < lon1 \
                and row["ELEVATION"] is not None:
            triplet = f"{row['LOCATION_ID']}:BCASWS"
            found[triplet] = Station(triplet, row["LOCATION_NAME"], row["LATITUDE"], row["LONGITUDE"],
                                     float(row["ELEVATION"]), source="bcasws")
    return found
