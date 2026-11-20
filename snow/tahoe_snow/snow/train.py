"""Fit, test, and select the snow model; write the report the site links to."""
import json

import numpy as np
import pandas as pd
from sklearn.base import clone

from tahoe_snow.config import MM_PER_IN, REPORTS, STATIONS, TABLES
from tahoe_snow.snow import dataset, features, phase, ratio
from tahoe_snow.snow.model import SnowModel


def load_events() -> pd.DataFrame:
    return pd.read_parquet(TABLES / "events.parquet")


def ratio_tables(events: pd.DataFrame) -> dict:
    """Every cross-validation and transfer test for the snow ratio."""
    manual = dataset.ratio_filter(events[events["source"] == "manual"])
    snotel = dataset.ratio_filter(events[events["source"] == "snotel"])
    both = pd.concat([manual, snotel], ignore_index=True)
    out = {"counts": {"manual": len(manual), "snotel": len(snotel),
                      "manual_stations": int(manual["station"].nunique()),
                      "snotel_stations": int(snotel["station"].nunique())}}
    out["manual, held-out season"], _ = ratio.cross_validate(manual, by="season")
    out["manual, held-out station"], _ = ratio.cross_validate(manual, by="station")
    out["SNOTEL, held-out season"], _ = ratio.cross_validate(snotel, by="season")
    out["train manual, test SNOTEL"] = ratio.train_on_apply_to(manual, snotel)
    out["train SNOTEL, test manual"] = ratio.train_on_apply_to(snotel, manual)
    out["manual + SNOTEL, held-out season"], predictions = ratio.cross_validate(both, by="season")
    out["_both"] = both
    out["_predictions"] = predictions
    return out


def band_table(events: pd.DataFrame, predictions: dict, names: list) -> pd.DataFrame:
    """Snowfall error (inches) by temperature band for the named models."""
    bands = pd.cut(events["t0"], [-40, -10, -6, -3, 0, 10], labels=["< -10", "-10 to -6", "-6 to -3", "-3 to 0", "> 0"])
    rows = []
    for band in bands.cat.categories:
        mask = (bands == band).to_numpy()
        if mask.sum() < 10:
            continue
        row = {"temperature at site (C)": band, "events": int(mask.sum()),
               "observed ratio": float(events.loc[mask, "slr"].mean())}
        for name in names:
            row[name] = ratio.score(events[mask], predictions[name][mask])["snow_mae_in"]
        rows.append(row)
    return pd.DataFrame(rows).set_index("temperature at site (C)")


def station_hourly(profiles: dataset.Profiles) -> dict:
    """Hourly features and observed snow fraction for each SNOTEL station."""
    snotel = pd.read_parquet(TABLES / "snotel_daily.parquet").set_index("date")
    out = {}
    for station in STATIONS.values():
        hourly = features.hourly_features(profiles.at(station.lat, station.lon), station.elev_m).asfreq("h")
        gains = snotel[snotel["station"] == station.triplet]
        gains = gains[gains.index >= dataset.PROFILE_START]
        observed = phase.observed(gains)
        observed["end_utc"] = observed.index + pd.Timedelta(days=1, hours=dataset.PST_OFFSET_H)
        observed["season"] = dataset.season_of(observed.index)
        out[station.triplet] = (hourly, observed, station.elev_m)
    return out


def phase_errors(stations: dict, kind: str, params: dict) -> pd.DataFrame:
    """Per-day snow-water error for one rain/snow form across stations."""
    frames = []
    for triplet, (hourly, observed, elev_m) in stations.items():
        fraction = phase.hourly_fraction(hourly, elev_m, kind, params)
        predicted = phase.daily_fraction(hourly, fraction).reindex(observed["end_utc"]).to_numpy()
        frame = observed[["season", "liquid_mm", "fraction"]].copy()
        frame["error_mm"] = (predicted - frame["fraction"]) * frame["liquid_mm"]
        frame["station"] = triplet
        frames.append(frame.dropna(subset=["error_mm"]))
    return pd.concat(frames)


def fit_phase(stations: dict) -> tuple:
    """Choose each form's parameters on training seasons and score on the held-out season."""
    rows, best = [], {}
    for kind in phase.GRIDS:
        errors = {json.dumps(p): phase_errors(stations, kind, p) for p in phase.grid(kind)}
        seasons = sorted(next(iter(errors.values()))["season"].unique())
        held = []
        for season in seasons:
            train_mae = {key: frame.loc[frame["season"] != season, "error_mm"].abs().mean()
                         for key, frame in errors.items()}
            chosen = min(train_mae, key=train_mae.get)
            held.append(errors[chosen].loc[errors[chosen]["season"] == season, "error_mm"])
        held = pd.concat(held)
        overall = {key: frame["error_mm"].abs().mean() for key, frame in errors.items()}
        best[kind] = json.loads(min(overall, key=overall.get))
        mixed = errors[json.dumps(best[kind])]
        mixed = mixed[mixed["fraction"].between(0.05, 0.95)]
        rows.append({"form": kind, "days": int(len(held)), "held-out error (mm water)": float(held.abs().mean()),
                     "held-out bias (mm water)": float(held.mean()),
                     "error on mixed days (mm water)": float(mixed["error_mm"].abs().mean()),
                     "mixed days": int(len(mixed)), "parameters": json.dumps(best[kind])})
    table = pd.DataFrame(rows).set_index("form")
    return table, best


def end_to_end(events: pd.DataFrame, stations: dict, ratio_name: str, phase_kind: str,
               phase_params: dict) -> pd.DataFrame:
    """Observed liquid in, daily snowfall out, at SNOTEL sites on every wet day of each held-out season.

    Includes rain and mixed days, which the ratio tests exclude. The ratio model is refit without
    the scored season; the liquid is spread over the day's hours by the model's precipitation.
    """
    trainable = dataset.ratio_filter(events)
    model_spec = ratio.candidates()[ratio_name]
    rows = []
    for season in sorted(trainable["season"].unique()):
        train = trainable[trainable["season"] != season]
        fitted = clone(model_spec)
        if isinstance(fitted, ratio.ColumnModel):
            fitted.fit(train, train["slr"].to_numpy(), sample_weight=np.sqrt(train["liquid_mm"].to_numpy()))
        else:
            fitted.fit(train, train["slr"].to_numpy())
        snow_model = SnowModel(fitted, phase_kind, phase_params)
        for triplet, (hourly, observed, elev_m) in stations.items():
            days = events[(events["station"] == triplet) & (events["season"] == season)
                          & (events["liquid_mm"].clip(lower=0).fillna(0) + events["prec_gain_mm"].fillna(0) > 0)]
            days = days[np.maximum(days["liquid_mm"], days["prec_gain_mm"]) >= 2.5]
            for day in days.itertuples():
                end = day.date + pd.Timedelta(days=1, hours=dataset.PST_OFFSET_H)
                window = hourly.loc[end - pd.Timedelta(hours=23):end]
                if len(window) < 24 or window[["t0", "tw0"]].isna().any().any():
                    continue
                weights = window["precip"].fillna(0.0)
                weights = weights / weights.sum() if weights.sum() >= 0.5 else pd.Series(1 / 24, index=window.index)
                liquid_total = max(day.liquid_mm, day.prec_gain_mm)
                result = snow_model.snowfall(window, weights * liquid_total, elev_m)
                kuchera = ratio.Kuchera().predict(window)
                rows.append({
                    "station": triplet, "season": season, "date": day.date, "liquid_mm": liquid_total,
                    "observed_cm": max(day.snow_mm, 0.0) / 10.0,
                    "snow model": result["snow_cm"].sum(),
                    "Kuchera + our rain/snow split":
                        (result["liquid_mm"] * result["snow_fraction"] * kuchera).sum() / 10,
                    "10:1 + our rain/snow split": (result["liquid_mm"] * result["snow_fraction"]).sum(),
                    "10:1, snow below 1 C": (result["liquid_mm"] * (window["t0"] < 1.0)).sum(),
                    "7:1, snow below 0 C (Open-Meteo style)": 0.7 * (result["liquid_mm"] * (window["t0"] < 0.0)).sum(),
                })
    return pd.DataFrame(rows)


def end_to_end_table(days: pd.DataFrame) -> pd.DataFrame:
    methods = [c for c in days.columns if c not in ("station", "season", "date", "liquid_mm", "observed_cm")]
    rows = []
    for method in methods:
        error_in = (days[method] - days["observed_cm"]) / (MM_PER_IN / 10)
        snowy = days["observed_cm"] >= 2.5
        rows.append({"method": method, "days": int(len(days)), "error (in)": float(error_in.abs().mean()),
                     "bias (in)": float(error_in.mean()),
                     "error on days with 1 in or more (in)": float(error_in[snowy].abs().mean()),
                     "error on days with 6 in or more (in)":
                         float(error_in[days["observed_cm"] >= 15.24].abs().mean())})
    return pd.DataFrame(rows).set_index("method")


def markdown(table: pd.DataFrame, digits: int = 2) -> str:
    return table.round(digits).to_markdown()


def write_report(sections: list) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "snow_model.md").write_text("\n\n".join(sections) + "\n")
