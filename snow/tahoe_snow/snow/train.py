"""Fit, test, and select the snow model; write the report the site links to."""
import json

import numpy as np
import pandas as pd
from sklearn.base import clone

from tahoe_snow.config import MM_PER_IN, MODELS, REPORTS, STATIONS, TABLES, levels_for
from tahoe_snow.snow import dataset, features, observations, phase, ratio
from tahoe_snow.snow.model import SnowModel
from tahoe_snow.sources import omfiles_s3

# The months a rain/snow split is fitted on outside the Sierra: summer rain says nothing about where the line sits.
SPLIT_MONTHS = (10, 11, 12, 1, 2, 3, 4, 5)


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


def sensor_hourly(stations: dict, gains: pd.DataFrame, profiles: dict) -> dict:
    """Hourly features and observed snow fraction for each of ``stations``, from a table of their daily gains and
    the block of 0.25-degree profiles around them (``omfiles_s3.block_profiles``)."""
    out = {}
    for station in stations.values():
        node = (round(round(station.lat / 0.25) * 0.25, 3), round(round(station.lon / 0.25) * 0.25, 3))
        hourly = features.hourly_features(profiles[node], station.elev_m).asfreq("h")
        observed = phase.observed(gains[gains["station"] == station.triplet].set_index("date"))
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


# Where a region's rain/snow split and snow ratio are fitted or checked: its box of stations
# (``observations.BOXES``) and the block of the upper-air archive over it.
REGION_BOXES = {"seattle": ("cascades", omfiles_s3.CASCADES_BLOCK), "tetons": ("tetonbox", omfiles_s3.TETONS_BLOCK),
                "wasatch": ("wasatchbox", omfiles_s3.WASATCH_BLOCK),
                "colorado": ("coloradobox", omfiles_s3.COLORADO_BLOCK),
                "okanagan": ("okanaganbox", omfiles_s3.OKANAGAN_BLOCK),
                "bccoast": ("bccoastbox", omfiles_s3.BCCOAST_BLOCK),
                "powderhighway": ("powderhighwaybox", omfiles_s3.POWDERHIGHWAY_BLOCK),
                "eastkootenays": ("eastkootenaysbox", omfiles_s3.EASTKOOTENAYS_BLOCK),
                "rockies": ("rockiesbox", omfiles_s3.ROCKIES_BLOCK)}
# Canada's regions are here for their rain/snow splits alone. Their snow ratio is the Sierra's and cannot be checked
# on these boxes' hand-measured days: Canada's climate stations report snowfall and its water at exactly 10 to 1
# (78% of 1,156 snow days at 37 stations, 2023 to 2026, Whistler Roundhouse, Sun Peaks and Mt. Fidelity among them),
# so one is worked out from the other. On the 229 days at the 16 stations that measure both, all in valley towns,
# the Sierra's model missed by 0.69 in, a flat 10:1 by 0.64 and Kuchera by 0.99. ``check_region_ratio`` on a
# Canadian box would score the flat 10:1 near zero and mean nothing, so no check is kept for them.
# How many times a region's own snow day counts against a Sierra one where the two are fitted together. The Sierra
# model ran an inch fluffy on Wasatch snow, and at stations held out a fit with the Wasatch's days at ten times
# missed by 1.21 in, against 1.32 at equal weight and 1.31 on the Wasatch's days alone.
REGION_DAY_WEIGHT = {"wasatch": 10.0}


def pooled_weights(sierra_days: int, region_days: pd.DataFrame, region: str) -> np.ndarray:
    """What multiplies each day's usual weight in a fit of the Sierra's days followed by the region's."""
    return np.concatenate([np.ones(sierra_days), np.full(len(region_days), REGION_DAY_WEIGHT.get(region, 1.0))])


def region_profiles(region: str, end: str) -> dict:
    return omfiles_s3.block_profiles(dataset.RAW_ARCHIVE_START, end, REGION_BOXES[region][1], levels_for(region))


def fit_seattle_phase(end: str, kind: str = "wet-bulb logistic") -> pd.DataFrame:
    return fit_region_phase("seattle", end, kind)


def fit_region_phase(region: str, end: str, kind: str = "wet-bulb logistic") -> pd.DataFrame:
    """Fit a region's rain/snow split to every SNOTEL station in its box (``observations.pull_box`` first) and
    save it, in the form the Sierra uses unless told otherwise. Returns the table of held-out tests."""
    box = REGION_BOXES[region][0]
    states, bbox, _ = observations.BOXES[box]
    profiles = region_profiles(region, end)
    gains = pd.read_parquet(TABLES / f"{box}_daily.parquet")
    gains = gains[gains["date"].dt.month.isin(SPLIT_MONTHS)]
    stations = sensor_hourly(observations.box_stations(states, bbox), gains, profiles)
    table, best = fit_phase(stations)
    # For the scorecard: the same days scored with everything called snow, and with the Sierra's curve as it is.
    sierra = phase_errors(stations, *phase.load())
    mixed = sierra[sierra["fraction"].between(0.05, 0.95)]
    table["all_snow_error"] = float(((1 - sierra["fraction"]) * sierra["liquid_mm"]).mean())
    table["sierra_error"] = float(sierra["error_mm"].abs().mean())
    table["sierra_mixed_error"] = float(mixed["error_mm"].abs().mean())
    table["stations"] = len(stations)
    table.to_csv(TABLES / f"phase_table_{region}.csv")
    phase.save(kind, best[kind], {"held_out_error_mm": float(table.loc[kind, "held-out error (mm water)"]),
                                  "stations": len(stations), "days": int(table.loc[kind, "days"])}, region=region)
    return table


def check_seattle_ratio(end: str) -> dict:
    return check_region_ratio("seattle", end)


def check_region_ratio(region: str, end: str) -> dict:
    """Score the Sierra-trained ratio model on a region's hand-measured snow days, against the simple methods and
    against refits that pool those days in, and keep the result beside the models. Nothing is refitted for use:
    the record says whether one should be."""
    events = dataset.ratio_filter(dataset.build_box(REGION_BOXES[region][0], end, region_profiles(region, end)))
    sierra = dataset.ratio_filter(load_events())
    sierra = sierra[sierra["source"] == "manual"]
    days = events[events["source"] == "manual"].reset_index(drop=True)
    model, spec = ratio.load(), ratio.candidates()["ridge (all)"]

    def brief(predicted) -> dict:
        scored = ratio.score(days, predicted)
        return {"snow_error_in": round(scored["snow_mae_in"], 2), "snow_bias_in": round(scored["snow_bias_in"], 2),
                "ratio_bias": round(scored["slr_bias"], 2)}

    def pooled(by: str) -> dict:
        predicted = np.full(len(days), np.nan)
        for group in pd.unique(days[by]):
            test = (days[by] == group).to_numpy()
            train = pd.concat([sierra, days[~test]])
            weight = np.sqrt(train["liquid_mm"].to_numpy()) * pooled_weights(len(sierra), days[~test], region)
            fitted = clone(spec).fit(train, train["slr"].to_numpy(), sample_weight=weight)
            predicted[test] = fitted.predict(days[test])
        return brief(predicted)

    record = {"in_use": json.loads((MODELS / "snow_ratio.json").read_text())["model"] + ", trained in the Sierra",
              "checked_on": {"days": int(len(days)), "stations": int(days["station"].nunique()),
                             "first_date": str(days["date"].min().date()), "last_date": str(days["date"].max().date()),
                             "sensor_days_not_used": int((events["source"] == "snotel").sum())},
              "sierra_model": brief(model.predict(days)), "kuchera": brief(ratio.Kuchera().predict(days)),
              "flat_10_to_1": brief(np.full(len(days), 10.0)),
              "pooled_refit_each_winter_held_out": pooled("season"),
              "pooled_refit_each_station_held_out": pooled("station")}
    (MODELS / f"snow_ratio_check_{region}.json").write_text(json.dumps(record, indent=2))
    return record


def fit_region_ratio(region: str, where: str, name: str = "ridge (all)") -> ratio.ColumnModel:
    """Fit a region's own ratio model and save it: the Sierra's form, trained on the Sierra's hand-measured snow
    days with the region's added (the table ``check_region_ratio`` leaves). ``where`` says so in the forecast's
    description of itself."""
    sierra = dataset.ratio_filter(load_events())
    days = dataset.ratio_filter(pd.read_parquet(TABLES / f"events_{REGION_BOXES[region][0]}.parquet"))
    days = days[days["source"] == "manual"]
    sierra = sierra[sierra["source"] == "manual"]
    both = pd.concat([sierra, days], ignore_index=True)
    extra = {"region_events": int(len(days)), "region_stations": int(days["station"].nunique())}
    if region in REGION_DAY_WEIGHT:
        extra["region_day_weight"] = REGION_DAY_WEIGHT[region]
    return ratio.fit_final(both, name, ratio.candidates()[name], region=region, where=where, extra=extra,
                           weights=pooled_weights(len(sierra), days, region))


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
