"""Fit the liquid bias correction from archived model precipitation and the snow sensors, one region at a time,
and test it on held-out seasons."""
import json
from concurrent.futures import ThreadPoolExecutor

import fsspec
import numpy as np
import omfiles
import pandas as pd

from tahoe_snow import biascorrect, blend
from tahoe_snow import config
from tahoe_snow.config import (BCCOAST_BBOX, BCCOAST_STATIONS, COLORADO_BBOX, COLORADO_STATIONS, EASTKOOTENAYS_BBOX,
                               EASTKOOTENAYS_STATIONS, MAMMOTH_BBOX, MAMMOTH_STATIONS, MODELS, OKANAGAN_BBOX,
                               OKANAGAN_STATIONS, POWDERHIGHWAY_BBOX, POWDERHIGHWAY_STATIONS, RAW, ROCKIES_BBOX,
                               ROCKIES_STATIONS, SEATTLE_BBOX, SEATTLE_STATIONS, SHASTA_BBOX, SHASTA_STATIONS,
                               STATIONS, TABLES, TAHOE_BBOX, TETONS_BBOX, TETONS_STATIONS, WASATCH_BBOX,
                               WASATCH_STATIONS)
from tahoe_snow.snow import dataset, phase

BUCKET = "openmeteo/data"
# Open-Meteo forecast model name -> archive folder.
ARCHIVES = {"gfs_seamless": "ncep_gfs013", "ecmwf_ifs025": "ecmwf_ifs025", "icon_seamless": "dwd_icon",
            "gem_seamless": "cmc_gem_gdps"}
PST_OFFSET_H = 8
WINTER_MONTHS = (11, 12, 1, 2, 3, 4)
# Per region: the stations, the box of archive to read around them, and the table of their daily gains.
# Tahoe keeps the file names it had before there were regions.
REGIONS = {"tahoe": (STATIONS, TAHOE_BBOX, "snotel_daily"),
           "mammoth": (MAMMOTH_STATIONS, MAMMOTH_BBOX, "mammoth_daily"),
           "seattle": (SEATTLE_STATIONS, SEATTLE_BBOX, "seattle_daily"),
           "tetons": (TETONS_STATIONS, TETONS_BBOX, "tetons_daily"),
           "wasatch": (WASATCH_STATIONS, WASATCH_BBOX, "wasatch_daily"),
           "colorado": (COLORADO_STATIONS, COLORADO_BBOX, "colorado_daily"),
           "shasta": (SHASTA_STATIONS, SHASTA_BBOX, "shasta_daily"),
           **{region: ({key: s for key, s in stations.items() if s.source == "bcasws" and s.corrects}, bbox,
                       f"{region}_daily")
              for region, stations, bbox in (("okanagan", OKANAGAN_STATIONS, OKANAGAN_BBOX),
                                             ("bccoast", BCCOAST_STATIONS, BCCOAST_BBOX),
                                             ("powderhighway", POWDERHIGHWAY_STATIONS, POWDERHIGHWAY_BBOX),
                                             ("eastkootenays", EASTKOOTENAYS_STATIONS, EASTKOOTENAYS_BBOX),
                                             ("rockies", ROCKIES_STATIONS, ROCKIES_BBOX))},
           # The third collector's six, each fitted to the SNOTEL stations within 25 km of its mountains.
           **{region: (getattr(config, f"{region.upper()}_STATIONS"), getattr(config, f"{region.upper()}_BBOX"),
                       f"{region}_daily")
              for region in ("montana", "sunvalley", "oregon", "newmexico", "alaska", "swcolorado")}}
# Hours behind UTC of the clock a region's sensors stamp their daily values on, where it is not the Pacific
# standard clock: Alaska's SNOTEL stations keep Alaska standard time.
SENSOR_OFFSET_H = {"alaska": 9}
# Shasta is here so its test can be run again, not because it has a correction: its pillows are low and measure
# snow alone, so on the days it rained at them the models look wet (2.7 times the pillows' water on days above
# freezing, 1.1 times on all-snow days, 2024 to 2026). A curve fitted to them would take the rain out of the water
# before the rain-or-snow split takes it out again, so none is saved.
# Canada's five are British Columbia's stations, read from the province's long record (``bcasws.daily``). On the
# 2024 to 2026 winters held out in turn the four-model average carried 53% of the measured water in the Okanagan,
# 61% on the Powder Highway and in the East Kootenays, 59% in the Rockies and 82% on the BC Coast, and 98 to 107%
# corrected. On the coast five stations that pair with no mountain did a little worse with their own curve than
# raw (Callaghan Creek, 12 km from Whistler, 0.50 to 0.61 in over three days): test again before pairing one.
# A pillow reading this much water on a day when no model had any, that day or the days beside it, is a sensor
# fault (a step in the reading), not a storm.
PHANTOM_MM, DRY_MM = 25.0, 2.0
# Stations whose own curve did worse on held-out winters than the curve pooled over their region, so they get the
# pooled one. Morse Lake and Pigtail Peak, east of the crest: the models were half as wet as these two in the 2024
# and 2025 winters and nearly as wet in 2026, so a curve from two winters overshot the third (3-day error on storms
# of 2 in or more: 1.43 and 1.13 in with their own curves, 1.04 and 1.00 with the pooled one, 1.16 and 1.02 raw).
# Soldier R.S., at Soldier Mountain's base, where the models are already right (101% of the measured water): its own
# curve missed three-day storms of 2 in or more by 0.50 in on the held-out winters, the pooled one by 0.28, and
# over all three-day spans 0.24 in against 0.23 (raw 0.22).
POOLED_ONLY = {"seattle": ("642:WA:SNTL", "692:WA:SNTL"), "sunvalley": ("769:ID:SNTL",)}


def suffix(region: str) -> str:
    return "" if region == "tahoe" else f"_{region}"


def archive_info(folder: str) -> dict:
    fs = fsspec.filesystem("s3", anon=True)
    meta = json.loads(fs.cat(f"{BUCKET}/{folder}/static/meta.json"))
    chunks = sorted(int(key.split("chunk_")[1].split(".")[0]) for key in fs.ls(f"{BUCKET}/{folder}/precipitation")
                    if "chunk_" in key)
    surface = omfiles.OmFileReader.from_fsspec(fs, f"{BUCKET}/{folder}/static/HSURF.om")
    return {"chunk_steps": meta["chunk_time_length"], "step_s": meta["temporal_resolution_seconds"], "chunks": chunks,
            "shape": tuple(surface.shape[:2]), "surface": surface}


def grid_index(shape: tuple, lat: float, lon: float) -> tuple:
    """Nearest point on a regular global grid (south to north, -180 eastward)."""
    ny, nx = shape
    return int(round((lat + 90) / 180 * (ny - 1))), int(round((lon + 180) / 360 * nx)) % nx


def read_chunk(folder: str, chunk: int, info: dict, iy: slice, ix: slice) -> np.ndarray:
    path = RAW / "om_precip" / f"{folder}_{chunk}_{iy.start}-{iy.stop}_{ix.start}-{ix.stop}.npy"
    if path.exists():
        return np.load(path)
    fs = fsspec.filesystem("s3", anon=True)
    reader = omfiles.OmFileReader.from_fsspec(fs, f"{BUCKET}/{folder}/precipitation/chunk_{chunk}.om")
    if len(reader.shape) == 3:
        block = np.asarray(reader[iy, ix, :], dtype=np.float32)
    else:
        nx = info["shape"][1]
        block = np.stack([np.asarray(reader[row * nx + ix.start:row * nx + ix.stop, :], dtype=np.float32)
                          for row in range(iy.start, iy.stop)])
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, block)
    return block


def archived_daily(model: str, stations: dict = STATIONS, bbox: tuple = TAHOE_BBOX,
                   offset_h: int = PST_OFFSET_H) -> pd.DataFrame:
    """Daily model precipitation at each station inside ``bbox``, from the archive, on the sensors' clock
    (Pacific Standard Time unless ``offset_h`` says otherwise)."""
    folder = ARCHIVES[model]
    info = archive_info(folder)
    lat0, lat1, lon0, lon1 = bbox
    y0, x0 = grid_index(info["shape"], lat0, lon0)
    y1, x1 = grid_index(info["shape"], lat1, lon1)
    iy, ix = slice(y0 - 1, y1 + 2), slice(x0 - 1, x1 + 2)
    with ThreadPoolExecutor(12) as pool:
        blocks = list(pool.map(lambda chunk: read_chunk(folder, chunk, info, iy, ix), info["chunks"]))
    step = pd.Timedelta(seconds=info["step_s"])
    times = pd.DatetimeIndex(np.concatenate([
        pd.date_range(pd.Timestamp(0) + chunk * info["chunk_steps"] * step, periods=info["chunk_steps"], freq=step)
        for chunk in info["chunks"]]))
    cube = np.concatenate(blocks, axis=2)
    frames = []
    for station in stations.values():
        sy, sx = grid_index(info["shape"], station.lat, station.lon)
        series = pd.Series(cube[sy - iy.start, sx - ix.start], index=times, dtype=float)
        # A value covers the step ending at its timestamp; shift so days run midnight to midnight PST.
        local_day = (series.index - step - pd.Timedelta(hours=offset_h)).normalize()
        daily = series.groupby(local_day).sum(min_count=int(0.9 * pd.Timedelta(days=1) / step))
        frames.append(pd.DataFrame({"model": model, "station": station.triplet, "date": daily.index,
                                    "forecast_mm": daily.to_numpy(),
                                    "grid_elev_m": float(info["surface"][sy, sx])}))
    return pd.concat(frames, ignore_index=True)


def observed_daily(table: str = "snotel_daily") -> pd.DataFrame:
    """Daily observed liquid at each station: the larger of the gauge and pillow gains (the pillow alone at the
    CDEC sites, whose gauges do not track their pillows)."""
    snotel = pd.read_parquet(TABLES / f"{table}.parquet")
    if "prec_gain_mm" not in snotel:
        # A region of CDEC pillows alone has no gauges.
        snotel["prec_gain_mm"] = np.nan
    liquid = np.maximum(snotel["prec_gain_mm"].fillna(-1), snotel["swe_gain_mm"].fillna(-1))
    both_missing = snotel["prec_gain_mm"].isna() & snotel["swe_gain_mm"].isna()
    return pd.DataFrame({"station": snotel["station"], "date": snotel["date"],
                         "observed_mm": liquid.where(~both_missing).clip(lower=0)})


def without_phantoms(table: pd.DataFrame) -> pd.DataFrame:
    """Drop station-days where the sensor shows a big gain that no model had on that day or its neighbors."""
    wettest = table.groupby(["station", "date"])["forecast_mm"].max().rename("wettest").reset_index()
    wettest = wettest.sort_values(["station", "date"])
    by_station = wettest.groupby("station")["wettest"]
    wettest["nearby"] = np.fmax(wettest["wettest"], np.fmax(by_station.shift(1), by_station.shift(-1)))
    table = table.merge(wettest[["station", "date", "nearby"]], on=["station", "date"])
    phantom = (table["observed_mm"] >= PHANTOM_MM) & (table["nearby"] < DRY_MM)
    return table[~phantom].drop(columns="nearby")


def pairs(region: str = "tahoe") -> pd.DataFrame:
    stations, bbox, observed = REGIONS[region]
    offset_h = SENSOR_OFFSET_H.get(region, PST_OFFSET_H)
    forecast = pd.concat([archived_daily(model, stations, bbox, offset_h) for model in ARCHIVES], ignore_index=True)
    table = forecast.merge(observed_daily(observed), on=["station", "date"]).dropna(
        subset=["forecast_mm", "observed_mm"])
    table = table[table["date"].dt.month.isin(WINTER_MONTHS)].copy()
    if any(station.source in ("cdec", "bcasws") for station in stations.values()):
        table = without_phantoms(table)
    table["season"] = dataset.season_of(table["date"])
    table["lead_day"] = 0
    table.to_parquet(TABLES / f"bias_pairs{suffix(region)}.parquet")
    return table


def fit(table: pd.DataFrame, region: str = "tahoe") -> biascorrect.Correction:
    """The region's correction: a curve per station, less the stations that are given the pooled curve."""
    correction = biascorrect.fit(table)
    for by_station in correction.maps.values():
        for station in POOLED_ONLY.get(region, ()):
            by_station.pop(station, None)
    return correction


def score(frame: pd.DataFrame, column: str) -> dict:
    """Error on wet days, where a day is wet if the station or the raw model had at least 1 mm."""
    wet = frame[np.maximum(frame["forecast_mm"], frame["observed_mm"]) >= phase.MIN_PRECIP_MM / 5]
    error = wet[column] - wet["observed_mm"]
    big = wet["observed_mm"] >= 25.4
    return {"wet days": int(len(wet)), "error (in)": float(error.abs().mean() / 25.4),
            "total forecast / observed": float(wet[column].sum() / wet["observed_mm"].sum()),
            "error on 1 in+ days (in)": float(error[big].abs().mean() / 25.4)}


def held_out_test(table: pd.DataFrame, season: int, region: str = "tahoe") -> pd.DataFrame:
    """Fit on every other season, score on ``season``: raw against corrected, per model and blended."""
    train, test = table[table["season"] != season], table[table["season"] == season].copy()
    correction = fit(train, region)
    test["corrected_mm"] = np.nan
    for (model, station), rows in test.groupby(["model", "station"]):
        test.loc[rows.index, "corrected_mm"] = correction.apply(model, station, 0, rows["forecast_mm"].to_numpy())
    out = []
    for model, rows in test.groupby("model"):
        out.append({"model": model, "water": "raw", **score(rows, "forecast_mm")})
        out.append({"model": model, "water": "corrected", **score(rows, "corrected_mm")})
    blend = test.groupby(["station", "date"]).agg(
        forecast_mm=("forecast_mm", "mean"), corrected_mm=("corrected_mm", "mean"),
        observed_mm=("observed_mm", "first"), models=("model", "size"))
    blend = blend[blend["models"] == test["model"].nunique()]
    out.append({"model": "blend of all", "water": "raw", **score(blend, "forecast_mm")})
    out.append({"model": "blend of all", "water": "corrected", **score(blend, "corrected_mm")})
    return pd.DataFrame(out)


def fit_and_save(table: pd.DataFrame, region: str = "tahoe") -> biascorrect.Correction:
    """Each region has its own file, so its stations are pooled only with each other."""
    correction = fit(table, region)
    (MODELS / f"bias{suffix(region)}.json").write_text(json.dumps(biascorrect.to_json(correction)))
    return correction


def save_weights(tests: pd.DataFrame, region: str, seasons: tuple = (2025, 2026)) -> dict:
    """Blend weights for a region from its held-out tests (``held_out_test`` for each season, with a ``season``
    column): each model weighted by the inverse of its corrected daily error, averaged over ``seasons``."""
    rows = tests[(tests["water"] == "corrected") & tests["season"].isin(seasons) & (tests["model"].isin(ARCHIVES))]
    errors = rows.groupby("model")["error (in)"].mean().to_dict()
    weights = {model: round(weight, 3) for model, weight in blend.inverse_error_weights(errors).items()}
    (MODELS / f"weights{suffix(region)}.json").write_text(json.dumps(weights))
    return weights


def storm_test(table: pd.DataFrame, seasons: tuple = (2025, 2026), region: str = "tahoe") -> pd.DataFrame:
    """Raw four-model average against the corrected one on held-out seasons: daily, 3-day, and big-storm error."""
    models = sorted(table["model"].unique())
    wide = table.pivot_table(index=["station", "date", "season"], columns="model", values="forecast_mm").join(
        table.groupby(["station", "date", "season"])["observed_mm"].first()).dropna().reset_index()
    wide["raw"] = wide[models].mean(axis=1)
    rows = []
    for season in seasons:
        correction = fit(table[table["season"] != season], region)
        test = wide[wide["season"] == season].copy()
        test["corrected"] = np.mean([[correction.apply(m, station, 0, np.array([value]))[0]
                                      for station, value in zip(test["station"], test[m])] for m in models], axis=0)
        for column in ("raw", "corrected"):
            wet = test[np.maximum(test["raw"], test["observed_mm"]) >= 1]
            error = wet[column] - wet["observed_mm"]
            ordered = test.sort_values(["station", "date"])
            columns = list(dict.fromkeys([column, "observed_mm", "raw"]))
            three = ordered.groupby("station")[columns].rolling(3).sum().dropna()
            three = three[np.maximum(three["raw"], three["observed_mm"]) >= 5]
            miss = (three[column] - three["observed_mm"]).abs()
            rows.append({"season": season, "method": column, "daily err in": error.abs().mean() / 25.4,
                         "total f/o": wet[column].sum() / wet["observed_mm"].sum(),
                         "1in+ day err": error[wet["observed_mm"] >= 25.4].abs().mean() / 25.4,
                         "3-day err in": miss.mean() / 25.4,
                         "3-day 2in+ err": miss[three["observed_mm"] >= 50.8].mean() / 25.4})
    out = pd.DataFrame(rows)
    out.to_csv(TABLES / f"bias_methods{suffix(region)}.csv", index=False)
    return out
