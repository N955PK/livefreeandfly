"""Fit the liquid bias correction from archived model precipitation and SNOTEL, and test it on a held-out season."""
import json
from concurrent.futures import ThreadPoolExecutor

import fsspec
import numpy as np
import omfiles
import pandas as pd

from tahoe_snow import biascorrect
from tahoe_snow.config import MODELS, RAW, STATIONS, TABLES, TAHOE_BBOX
from tahoe_snow.snow import dataset, phase

BUCKET = "openmeteo/data"
# Open-Meteo forecast model name -> archive folder.
ARCHIVES = {"gfs_seamless": "ncep_gfs013", "ecmwf_ifs025": "ecmwf_ifs025", "icon_seamless": "dwd_icon",
            "gem_seamless": "cmc_gem_gdps"}
PST_OFFSET_H = 8
WINTER_MONTHS = (11, 12, 1, 2, 3, 4)


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


def archived_daily(model: str) -> pd.DataFrame:
    """Daily (Pacific Standard Time) model precipitation at each SNOTEL station, from the archive."""
    folder = ARCHIVES[model]
    info = archive_info(folder)
    lat0, lat1, lon0, lon1 = TAHOE_BBOX
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
    for station in STATIONS.values():
        sy, sx = grid_index(info["shape"], station.lat, station.lon)
        series = pd.Series(cube[sy - iy.start, sx - ix.start], index=times, dtype=float)
        # A value covers the step ending at its timestamp; shift so days run midnight to midnight PST.
        local_day = (series.index - step - pd.Timedelta(hours=PST_OFFSET_H)).normalize()
        daily = series.groupby(local_day).sum(min_count=int(0.9 * pd.Timedelta(days=1) / step))
        frames.append(pd.DataFrame({"model": model, "station": station.triplet, "date": daily.index,
                                    "forecast_mm": daily.to_numpy(),
                                    "grid_elev_m": float(info["surface"][sy, sx])}))
    return pd.concat(frames, ignore_index=True)


def observed_daily() -> pd.DataFrame:
    """Daily observed liquid at each SNOTEL station: the larger of the gauge and pillow gains."""
    snotel = pd.read_parquet(TABLES / "snotel_daily.parquet")
    liquid = np.maximum(snotel["prec_gain_mm"].fillna(-1), snotel["swe_gain_mm"].fillna(-1))
    both_missing = snotel["prec_gain_mm"].isna() & snotel["swe_gain_mm"].isna()
    return pd.DataFrame({"station": snotel["station"], "date": snotel["date"],
                         "observed_mm": liquid.where(~both_missing).clip(lower=0)})


def pairs() -> pd.DataFrame:
    forecast = pd.concat([archived_daily(model) for model in ARCHIVES], ignore_index=True)
    table = forecast.merge(observed_daily(), on=["station", "date"]).dropna(subset=["forecast_mm", "observed_mm"])
    table = table[table["date"].dt.month.isin(WINTER_MONTHS)].copy()
    table["season"] = dataset.season_of(table["date"])
    table["lead_day"] = 0
    table.to_parquet(TABLES / "bias_pairs.parquet")
    return table


def score(frame: pd.DataFrame, column: str) -> dict:
    """Error on wet days, where a day is wet if the station or the raw model had at least 1 mm."""
    wet = frame[np.maximum(frame["forecast_mm"], frame["observed_mm"]) >= phase.MIN_PRECIP_MM / 5]
    error = wet[column] - wet["observed_mm"]
    big = wet["observed_mm"] >= 25.4
    return {"wet days": int(len(wet)), "error (in)": float(error.abs().mean() / 25.4),
            "total forecast / observed": float(wet[column].sum() / wet["observed_mm"].sum()),
            "error on 1 in+ days (in)": float(error[big].abs().mean() / 25.4)}


def held_out_test(table: pd.DataFrame, season: int) -> pd.DataFrame:
    """Fit on every other season, score on ``season``: raw against corrected, per model and blended."""
    train, test = table[table["season"] != season], table[table["season"] == season].copy()
    correction = biascorrect.fit(train)
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


def fit_and_save(table: pd.DataFrame) -> biascorrect.Correction:
    correction = biascorrect.fit(table)
    (MODELS / "bias.json").write_text(json.dumps(biascorrect.to_json(correction)))
    return correction


def storm_test(table: pd.DataFrame, seasons: tuple = (2025, 2026)) -> pd.DataFrame:
    """Raw four-model average against the corrected one on held-out seasons: daily, 3-day, and big-storm error."""
    models = sorted(table["model"].unique())
    wide = table.pivot_table(index=["station", "date", "season"], columns="model", values="forecast_mm").join(
        table.groupby(["station", "date", "season"])["observed_mm"].first()).dropna().reset_index()
    wide["raw"] = wide[models].mean(axis=1)
    rows = []
    for season in seasons:
        correction = biascorrect.fit(table[table["season"] != season])
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
    out.to_csv(TABLES / "bias_methods.csv", index=False)
    return out
