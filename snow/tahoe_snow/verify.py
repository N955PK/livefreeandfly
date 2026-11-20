"""Scorecard for the site, assembled from the held-out tests saved while fitting."""
import json

import pandas as pd

from tahoe_snow.config import DATA, TABLES
from tahoe_snow.snow import phase

RATIO_ROWS = {"fixed 10:1": "Flat 10:1", "Kuchera": "Kuchera (the common free method)",
              "ridge (all)": "This site's trained ratio"}
WATER_ROWS = {"raw": "Raw four-model average", "qm each model": "Corrected to SNOTEL (in use)"}
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
                 f"{int(split['days'].iloc[0]):,} held-out days. The three methods are close; calling everything "
                 "snow would miss by 4.9 mm.",
         "columns": ["Method", "Error (mm of water)", "On mixed days (mm)"],
         "rows": [[label + (" (in use)" if key == in_use else ""), f"{split.loc[key, 'held-out error (mm water)']:.2f}",
                   f"{split.loc[key, 'error on mixed days (mm water)']:.2f}"] for key, label in PHASE_ROWS.items()]},
        {"title": "Water.",
         "note": "Model water against what 22 SNOTEL stations measured, on the 2025 and 2026 winters held out in "
                 "turn. Correction fixes the totals and big storms; ordinary single days get slightly worse, "
                 "because scaling a forecast up also scales up its misses.",
         "columns": ["Method", "Total vs measured", "Daily error (in)", "3-day error (in)",
                     "3-day error, 2 in+ storms (in)"],
         "rows": [[label, f"{100 * water.loc[key, 'total f/o']:.0f}%", f"{water.loc[key, 'daily err in']:.2f}",
                   f"{water.loc[key, '3-day err in']:.2f}", f"{water.loc[key, '3-day 2in+ err']:.2f}"]
                  for key, label in WATER_ROWS.items()]},
        {"title": "Live forecasts.",
         "note": "Every forecast this page shows is archived and will be graded against the stations by lead "
                 "day as it comes due, including the ranges. That table starts filling in after the first week.",
         "columns": [], "rows": []},
    ]
    card = {"sections": sections}
    (DATA / "scorecard.json").write_text(json.dumps(card))
    return card
