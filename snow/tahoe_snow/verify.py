"""Scorecard for the site, assembled from the held-out tests saved while fitting."""
import json

import pandas as pd

from tahoe_snow.config import DATA, TABLES
from tahoe_snow.snow import phase

RATIO_ROWS = {"fixed 10:1": "Flat 10:1", "Kuchera": "Kuchera (the common free method)",
              "ridge (all)": "This site's trained ratio"}
WATER_ROWS = {"raw": "Raw four-model average", "corrected": "Corrected to the snow sensors (in use)"}
PHASE_ROWS = {"air temperature threshold": "Air-temperature cutoff", "wet-bulb snow level ramp": "Wet-bulb snow level",
              "wet-bulb logistic": "Wet-bulb curve"}


def scorecard() -> dict:
    ratio = pd.read_csv(TABLES / "ratio_cv_season.csv", index_col=0)
    in_use = phase.load()[0]
    water = pd.read_csv(TABLES / "bias_methods.csv").groupby("method").mean(numeric_only=True)
    split = pd.read_csv(TABLES / "phase_table.csv", index_col=0)
    sections = [
        {"title": "Snow ratio.",
         "note": f"Given the measured water, how far off is the snowfall? {int(ratio['n'].iloc[0]):,} hand-measured "
                 "Sierra snow days, 2021 to 2026; each winter is scored by a model that never saw it.",
         "columns": ["Method", "Snowfall error (in)", "Average miss (in)"],
         "rows": [[label, f"{ratio.loc[key, 'snow_mae_in']:.2f}", f"{ratio.loc[key, 'snow_bias_in']:+.2f}"]
                  for key, label in RATIO_ROWS.items()]},
        {"title": "Rain or snow.",
         "note": f"Water wrongly called rain or snow per wet day, at 22 Tahoe snow sensors over "
                 f"{int(split['days'].iloc[0]):,} held-out days. The three methods are tied; calling everything "
                 f"snow would miss by {float(split['all_snow_error'].iloc[0]):.1f} mm.",
         "columns": ["Method", "Error (mm of water)", "On mixed days (mm)"],
         "rows": [[label + (" (in use)" if key == in_use else ""), f"{split.loc[key, 'held-out error (mm water)']:.2f}",
                   f"{split.loc[key, 'error on mixed days (mm water)']:.2f}"] for key, label in PHASE_ROWS.items()]},
        {"title": "Water.",
         "note": "Model water against what 22 snow sensors measured, on the 2025 and 2026 winters held out in turn.",
         "columns": ["Method", "Total vs measured", "Daily error (in)", "3-day error (in)",
                     "3-day error, 2 in+ storms (in)"],
         "rows": [[label, f"{100 * water.loc[key, 'total f/o']:.0f}%", f"{water.loc[key, 'daily err in']:.2f}",
                   f"{water.loc[key, '3-day err in']:.2f}", f"{water.loc[key, '3-day 2in+ err']:.2f}"]
                  for key, label in WATER_ROWS.items()]},
    ]
    mammoth = TABLES / "bias_methods_mammoth.csv"
    if mammoth.exists():
        water = pd.read_csv(mammoth).groupby("method").mean(numeric_only=True)
        sections.append(
            {"title": "Water, Mammoth area.",
             "note": "The same test against 10 snow sensors along the crest around Mammoth, on the 2024, 2025, and "
                     "2026 winters held out in turn. Mammoth Mountain and Sherwin Ridge use the Mammoth Pass sensor; "
                     "June Mountain and Carson Peak have no working sensor nearby and are left uncorrected.",
             "columns": ["Method", "Total vs measured", "Daily error (in)", "3-day error (in)",
                         "3-day error, 2 in+ storms (in)"],
             "rows": [[label.replace(" (in use)", " (in use where a sensor is near)"),
                       f"{100 * water.loc[key, 'total f/o']:.0f}%", f"{water.loc[key, 'daily err in']:.2f}",
                       f"{water.loc[key, '3-day err in']:.2f}", f"{water.loc[key, '3-day 2in+ err']:.2f}"]
                      for key, label in WATER_ROWS.items()]})
    sections += [
        {"title": "Live forecasts.",
         "note": "Every forecast this page shows is archived and will be graded against the stations by lead "
                 "day as it comes due, including the ranges. That table starts filling in after the first week.",
         "columns": [], "rows": []},
    ]
    card = {"sections": sections}
    (DATA / "scorecard.json").write_text(json.dumps(card))
    return card
