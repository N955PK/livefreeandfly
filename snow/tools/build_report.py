"""Build the public "how we tested it" page: figures and numbers from the held-out tests.

Reads the cached training tables (run the fitting first) and writes report/index.html and report/*.png.
"""
import json
import warnings
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from tahoe_snow.config import MM_PER_IN, STATIONS, TABLES  # noqa: E402
from tahoe_snow.snow import dataset, phase, ratio, train  # noqa: E402

warnings.filterwarnings("ignore")
OUT = Path(__file__).resolve().parent.parent / "report"
INK, MUTED, GRID = "#0f1720", "#6b7480", "#e6e9ec"
BLUE, ORANGE, GRAY = "#2a78d6", "#eb6834", "#9aa3ad"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10.5, "axes.edgecolor": "#c5cad0", "axes.linewidth": 0.8,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.labelcolor": INK, "text.color": INK,
                     "xtick.color": MUTED, "ytick.color": MUTED, "axes.grid": True, "grid.color": GRID,
                     "grid.linewidth": 0.8, "axes.axisbelow": True, "figure.dpi": 100, "savefig.dpi": 200,
                     "savefig.bbox": "tight", "savefig.facecolor": "white"})


def save(fig, name: str) -> str:
    fig.savefig(OUT / name)
    plt.close(fig)
    return name


def ratio_figures(manual: pd.DataFrame, long: pd.DataFrame) -> dict:
    models = ratio.candidates()
    ours = ratio.out_of_fold(manual, models["ridge (all)"], "season")
    kuchera = ratio.Kuchera().predict(manual)
    flat = np.full(len(manual), 10.0)
    scores = {name: ratio.score(manual, np.clip(p, 3, 30) if name == "This site" else p)
              for name, p in [("Flat 10:1", flat), ("Kuchera", kuchera), ("This site", ours)]}
    out = {"n": len(manual), "stations": int(manual["station"].nunique()), "scores": scores}

    # 1. The data: 45 years of hand-measured snow ratios against temperature.
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    bins = np.arange(-14, 5, 2)
    groups = long.groupby(pd.cut(long["t0"], bins))["slr"]
    mid = [b.mid for b in groups.median().index]
    ax.fill_between(mid, groups.quantile(0.25), groups.quantile(0.75), color=BLUE, alpha=0.15, lw=0)
    ax.plot(mid, groups.median(), color=BLUE, lw=2, marker="o", ms=5)
    ax.text(mid[0] + 0.2, groups.quantile(0.75).iloc[0] + 0.4, "middle half of days", color=MUTED, fontsize=9.5)
    ax.set_xlabel("Temperature at the station during the snowfall (°C)")
    ax.set_ylabel("Inches of snow per inch of water")
    ax.set_ylim(0, 22)
    out["fig_data"] = save(fig, "ratio_vs_temperature.png")
    out["n_long"] = int(len(long))

    # 2. Predicted against measured ratio, this site and Kuchera.
    fig, axes = plt.subplots(1, 2, figsize=(7.6, 3.7), sharex=True, sharey=True)
    for ax, (name, pred, color) in zip(axes, [("Kuchera", kuchera, GRAY), ("This site", np.clip(ours, 3, 30), BLUE)]):
        ax.scatter(manual["slr"], pred, s=7, color=color, alpha=0.35, lw=0)
        ax.plot([0, 35], [0, 35], color=INK, lw=0.8)
        ax.set_title(f"{name}: off by {scores[name]['snow_mae_in']:.2f} in of snow on average", fontsize=10.5, loc="left")
        ax.set_xlim(0, 35)
        ax.set_ylim(0, 35)
        ax.set_xlabel("Measured ratio")
    axes[0].set_ylabel("Predicted ratio")
    out["fig_scatter"] = save(fig, "ratio_predicted_vs_measured.png")

    # 3. Snowfall error by temperature band.
    bands = pd.cut(manual["t0"], [-40, -8, -5, -3, -1, 5], labels=["below −8", "−8 to −5", "−5 to −3", "−3 to −1", "above −1"])
    rows = {name: [np.abs((p - manual["slr"]) * manual["liquid_mm"] / MM_PER_IN)[bands == band].mean()
                   for band in bands.cat.categories] for name, p in [("Flat 10:1", flat), ("Kuchera", kuchera), ("This site", ours)]}
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    xs = np.arange(len(bands.cat.categories))
    for k, (name, color) in enumerate([("Flat 10:1", "#c5cad0"), ("Kuchera", GRAY), ("This site", BLUE)]):
        ax.bar(xs + (k - 1) * 0.26, rows[name], width=0.24, color=color, label=name)
    ax.set_xticks(xs, [f"{b}\n{int((bands == b).sum())} days" for b in bands.cat.categories])
    ax.set_xlabel("Temperature at the station (°C)")
    ax.set_ylabel("Average snowfall error (in)")
    ax.legend(frameon=False, ncol=3, loc="upper right")
    ax.grid(axis="x", visible=False)
    out["fig_bands"] = save(fig, "ratio_error_by_temperature.png")

    # 4. Error by winter.
    by_season = pd.DataFrame({name: pd.Series(np.abs((p - manual["slr"]) * manual["liquid_mm"] / MM_PER_IN)).groupby(
        manual["season"].to_numpy()).mean() for name, p in [("Kuchera", kuchera), ("This site", ours)]})
    out["by_season"] = {int(season): {k: round(float(v), 2) for k, v in row.items()} for season, row in by_season.iterrows()}
    out["season_counts"] = {int(k): int(v) for k, v in manual["season"].value_counts().sort_index().items()}
    return out


def phase_figure(stations: dict) -> dict:
    kind, params = phase.load()
    rows = []
    for triplet, (hourly, observed, elev_m) in stations.items():
        wet = hourly["precip"].fillna(0.0)
        weighted = (hourly["tw0"] * wet).rolling(24, min_periods=24).sum() / wet.rolling(24, min_periods=24).sum().where(lambda s: s >= 0.5)
        frame = observed[["fraction", "liquid_mm"]].copy()
        frame["tw"] = weighted.reindex(observed["end_utc"]).to_numpy()
        rows.append(frame.dropna())
    days = pd.concat(rows)
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    ax.scatter(days["tw"], days["fraction"], s=6, color=GRAY, alpha=0.25, lw=0)
    bins = np.arange(-8, 8.1, 1)
    groups = days.groupby(pd.cut(days["tw"], bins))
    centers = [b.mid for b in groups["fraction"].mean().index]
    mean = groups.apply(lambda g: np.average(g["fraction"], weights=g["liquid_mm"]) if len(g) > 15 else np.nan)
    ax.plot(centers, mean, color=INK, lw=0, marker="o", ms=5, label="measured, averaged by degree")
    grid = np.linspace(-8, 8, 200)
    ax.plot(grid, 1 / (1 + np.exp((grid - params["center_c"]) / params["width_c"])), color=BLUE, lw=2, label="the curve in use")
    ax.set_xlabel("Wet-bulb temperature at the sensor's elevation, from the weather model (°C)")
    ax.set_ylabel("Share of the day's water that fell as snow")
    ax.legend(frameon=False, loc="lower left")
    return {"kind": kind, "params": params, "days": int(len(days)), "fig": save(fig, "rain_or_snow.png")}


def water_figures() -> dict:
    pairs = pd.read_parquet(TABLES / "bias_pairs.parquet")
    names = {"gfs_seamless": "GFS", "ecmwf_ifs025": "ECMWF", "icon_seamless": "ICON", "gem_seamless": "GEM"}
    ratios = pairs.groupby(["station", "model"]).apply(lambda g: g["forecast_mm"].sum() / g["observed_mm"].sum()).unstack()
    ratios.index = [STATIONS[s].name for s in ratios.index]
    ratios = ratios.loc[ratios.mean(axis=1).sort_values().index]
    fig, ax = plt.subplots(figsize=(7.2, 6.4))
    colors = {"gfs_seamless": BLUE, "ecmwf_ifs025": ORANGE, "icon_seamless": "#1baf7a", "gem_seamless": "#6250d6"}
    for model in names:
        ax.scatter(ratios[model] * 100, np.arange(len(ratios)), s=34, color=colors[model], label=names[model], zorder=3,
                   edgecolor="white", lw=0.8)
    ax.axvline(100, color=INK, lw=1)
    ax.set_yticks(np.arange(len(ratios)), ratios.index)
    ax.set_xlabel("Model's total water as a share of what the sensor measured (%)")
    ax.set_xlim(0, 180)
    ax.legend(frameon=False, ncol=4, loc="upper center", bbox_to_anchor=(0.5, 1.07))
    ax.grid(axis="y", visible=False)
    out = {"fig_stations": save(fig, "water_by_station.png"), "pairs": int(len(pairs)), "methods": {}}
    methods = pd.read_csv(TABLES / "bias_methods.csv").groupby("method").mean(numeric_only=True)
    for key, label in [("raw", "Raw average of four models"), ("corrected", "Corrected to the sensors (in use)")]:
        out["methods"][label] = {k: round(float(methods.loc[key, k]), 2) for k in ["total f/o", "daily err in", "3-day err in", "3-day 2in+ err"]}
    out["mammoth"] = mammoth_block(names)
    return out


def mammoth_block(names: dict) -> str:
    """The Mammoth-area water test, as HTML; empty until that region's tables exist."""
    if not (TABLES / "bias_methods_mammoth.csv").exists():
        return ""
    methods = pd.read_csv(TABLES / "bias_methods_mammoth.csv").groupby("method").mean(numeric_only=True)
    pairs = pd.read_parquet(TABLES / "bias_pairs_mammoth.parquet")
    # Only days every model covers, so the four shares are over the same storms.
    at_pass = pairs[pairs["station"] == "MHP:CDEC"]
    at_pass = at_pass[at_pass.groupby("date")["model"].transform("size") == len(names)]
    share = at_pass.groupby("model").apply(lambda g: g["forecast_mm"].sum() / g["observed_mm"].sum())
    shares = ", ".join(f"{names[model]} {100 * share[model]:.0f}%" for model in share.sort_values().index)
    rows = "".join(
        f"<tr><td>{label}</td><td>{100 * methods.loc[key, 'total f/o']:.0f}%</td><td>{methods.loc[key, 'daily err in']:.2f}</td>"
        f"<td>{methods.loc[key, '3-day err in']:.2f}</td><td>{methods.loc[key, '3-day 2in+ err']:.2f}</td></tr>"
        for key, label in [("raw", "Raw average of four models"), ("corrected", "Corrected to the Mammoth sensors (in use)")])
    return f"""
<h3>Around Mammoth</h3>
<p>Mammoth gets its own correction, fitted to {pairs['station'].nunique()} snow sensors along the crest from Virginia Lakes to Bishop Creek and tested the same way on the 2024, 2025, and 2026 winters. The Tahoe correction is not used there: on these sensors it did worse than no correction.</p>
<div class="scroll"><table><tr><th>Water forecast</th><th>Total vs measured</th><th>Daily error (in)</th><th>3-day error (in)</th><th>3-day error, 2 in+ storms</th></tr>{rows}</table></div>
<p><b>Mammoth Mountain and Sherwin Ridge</b> use the Mammoth Pass sensor, 2 km south of the summit. The models' shares of its measured water: {shares}. Those misses offset, so at this one sensor the corrected blend only ties the raw one; the correction is kept because it makes each model right on its own.</p>
<p><b>June Mountain and Carson Peak</b> have no working sensor nearby and are left uncorrected. The record of a sensor that has since gone quiet (Gem Pass) says a correction borrowed from Mammoth Pass would make them worse.</p>
<p><b>The sensors:</b> most are state snow pillows that are not quality-controlled the way SNOTEL is. Adding up their daily rises counts sensor jitter as snow (about 20% too much over a week), so readings are smoothed and small dips ignored before any of this is fitted or scored.</p>
"""


def page(ratio_out: dict, phase_out: dict, water_out: dict) -> str:
    s = ratio_out["scores"]
    season_rows = "".join(f"<tr><td>{season - 1}–{str(season)[2:]}</td><td>{ratio_out['season_counts'][season]}</td>"
                          f"<td>{row['Kuchera']:.2f}</td><td>{row['This site']:.2f}</td></tr>"
                          for season, row in ratio_out["by_season"].items())
    water_rows = "".join(f"<tr><td>{label}</td><td>{100 * m['total f/o']:.0f}%</td><td>{m['daily err in']:.2f}</td>"
                         f"<td>{m['3-day err in']:.2f}</td><td>{m['3-day 2in+ err']:.2f}</td></tr>"
                         for label, m in water_out["methods"].items())
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>How we tested it · Sierra Snow</title>
<link rel="icon" type="image/png" sizes="32x32" href="../icons/favicon-32.png">
<style>
body{{margin:0;background:#f4f6f8;color:#0f1720;font-family:system-ui,-apple-system,"Segoe UI",sans-serif;line-height:1.55}}
main{{max-width:780px;margin:0 auto;padding:28px 16px 56px}}
a{{color:#1c5cab}} h1{{font-size:30px;letter-spacing:-.02em;margin:8px 0 6px}} h2{{font-size:20px;margin:34px 0 6px}} h3{{font-size:16px;margin:24px 0 4px}}
p{{margin:0 0 12px;color:#333c46}} .lede{{font-size:17px}}
figure{{margin:14px 0 18px;background:#fff;border:1px solid rgba(15,23,32,.1);border-radius:14px;padding:12px}}
figure img{{width:100%;height:auto;display:block}} figcaption{{font-size:13px;color:#6b7480;margin-top:8px}}
table{{border-collapse:collapse;font-size:14px;margin:8px 0 14px;font-variant-numeric:tabular-nums}}
th,td{{padding:6px 12px;border-bottom:1px solid #e6e9ec;text-align:right}} th{{color:#6b7480;font-weight:550;font-size:12.5px}}
td:first-child,th:first-child{{text-align:left}} .scroll{{overflow-x:auto}}
</style></head><body><main>
<a href="../">← Sierra Snow</a>
<h1>How we tested it</h1>
<p class="lede">Every number here comes from winters or stations the model never saw while it was being fitted. Where something did not work, it says so.</p>

<h2>1. How fluffy the snow is</h2>
<p>The snow ratio is inches of snow per inch of water. It is the hardest part to predict and the part most forecasts guess at.
The raw material is {ratio_out['n_long']:,} days of snowfall measured by hand at Sierra stations since 1979. Colder storms make lighter snow, but with a lot of scatter.</p>
<figure><img src="{ratio_out['fig_data']}" alt="Median snow ratio falls from about 14 to 7 as temperature rises from −12 to +3 °C"><figcaption>The line is the middle day at each temperature; the band holds the middle half of days.</figcaption></figure>
<p>The model in use is fitted on {ratio_out['n']:,} hand-measured snow days at {ratio_out['stations']} stations from the five winters that have detailed upper-air data, using temperature, wind, and humidity aloft plus the amount of water.
Given the measured water, it misses the snowfall by <b>{s['This site']['snow_mae_in']:.2f} in</b> on average, against {s['Kuchera']['snow_mae_in']:.2f} in for Kuchera (the common free method) and {s['Flat 10:1']['snow_mae_in']:.2f} in for a flat 10:1.</p>
<figure><img src="{ratio_out['fig_scatter']}" alt="Predicted against measured snow ratio for Kuchera and for this site's model"><figcaption>Each dot is one station-day, predicted by a model fitted without that winter. A perfect forecast would sit on the line. Neither does: the ratio is noisy, and the model explains only about {100 * s['This site']['r2']:.0f}% of its day-to-day variation.</figcaption></figure>
<figure><img src="{ratio_out['fig_bands']}" alt="Average snowfall error by temperature band for three methods"><figcaption>Kuchera does worst in cold storms, where it calls for very light snow that the Sierra rarely delivers.</figcaption></figure>
<div class="scroll"><table><tr><th>Winter held out</th><th>Snow days</th><th>Kuchera error (in)</th><th>This site (in)</th></tr>{season_rows}</table></div>
<p><b>What did not work:</b> training on the full 45-year record. Its upper-air data is coarse and does not line up with the forecast models, so it made the forecasts slightly worse, and it is not used.</p>

<h2>2. Rain or snow</h2>
<p>At {phase_out['days']:,} wet days across 22 Tahoe snow sensors, the share of water that fell as snow is the snowpack's water gain divided by the precipitation. The curve in use turns the model's wet-bulb temperature into that share.</p>
<figure><img src="{phase_out['fig']}" alt="Measured snow share against wet-bulb temperature with the fitted curve"><figcaption>Gray dots are single days. Half the water falls as snow at a wet-bulb temperature of about {phase_out['params']['center_c']:.2f} °C.</figcaption></figure>
<p>Three methods were tried and came out tied: about 2.4 mm of water miscalled per wet day, half the 4.9 mm you get by calling everything snow.</p>
<p><b>A mistake we caught:</b> an earlier version of this test read the sensors' daily records one day off, which made every method look much worse and one winter look broken. Lining the dates up fixed both.</p>

<h2>3. How much water</h2>
<p>Weather models are consistently too dry or too wet at particular spots in the mountains. Each dot below is one model's total water at one sensor as a share of what the sensor measured ({water_out['pairs']:,} model-days).</p>
<figure><img src="{water_out['fig_stations']}" alt="Model water as a percentage of measured water at 22 stations for four models"><figcaption>100% is a perfect total. At Mt Rose every model delivers well under half the measured water.</figcaption></figure>
<p>Correcting each model to its nearest sensor improves every measure below, most of all the big storms.</p>
<p><b>Guards:</b> a corrected day is never allowed to exceed the wettest day its sensor has recorded, and the blend takes its amount from the middle models, so one model with a runaway correction cannot carry the total. (One model delivers 13% of the measured water at Mt Rose; uncapped, its correction once turned 43 mm into 247.)</p>
<div class="scroll"><table><tr><th>Water forecast</th><th>Total vs measured</th><th>Daily error (in)</th><th>3-day error (in)</th><th>3-day error, 2 in+ storms</th></tr>{water_rows}</table></div>
{water_out['mammoth']}
<h2>4. Wind gusts</h2>
<p>The weather models' own gust field runs low in the mountains, so above the base this site estimates gusts from the faster air 500 m higher up, which is where gusts come from.
Against 29,068 hours of measured gusts at the Palisades snow sensor (8,010 ft, five winters), the wind 500 m up tracks the measured gusts better than the wind at the sensor's own height: correlation 0.79 against 0.73, and an average miss of 5.7 mph against 6.7.</p>
<p><b>The limit:</b> that sensor sits in a sheltered spot and averages only 7 mph, and the one other free sensor is more sheltered still. So the method's shape is tested, but how strong gusts get on an exposed ridge is not. Treat ridge gusts as estimates.</p>

<h2>What is not tested yet</h2>
<p>These are backtests against model archives. Live forecasts made by this site are being saved and will be graded against the sensors by lead day as they come due, including the ± ranges. The correction is fitted on short-range model data and applied to every lead time, which is untested beyond a day or two.</p>
<p>Sources: NOAA GHCN-Daily and CoCoRaHS hand measurements, USDA SNOTEL sensors, California Data Exchange Center snow pillows, and model archives from Open-Meteo.</p>
</main></body></html>
"""


def main() -> None:
    OUT.mkdir(exist_ok=True)
    events = train.load_events()
    manual = dataset.ratio_filter(events[events["source"] == "manual"])
    manual = manual[manual["season"].between(2022, 2026)].reset_index(drop=True)
    long = dataset.ratio_filter(pd.read_parquet(TABLES / "events_long.parquet"))
    profiles = dataset.Profiles("2026-11-18", early_cells=dataset.profile_cells())
    ratio_out = ratio_figures(manual, long)
    phase_out = phase_figure(train.station_hourly(profiles))
    water_out = water_figures()
    (OUT / "index.html").write_text(page(ratio_out, phase_out, water_out))
    print(json.dumps({"ratio": ratio_out["scores"], "seasons": ratio_out["by_season"], "phase": phase_out, "water": water_out["methods"]},
                     indent=1)[:1500])


if __name__ == "__main__":
    main()
