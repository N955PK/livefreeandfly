"""Scorecard for the site, assembled from the held-out tests saved while fitting."""
import json

import pandas as pd

from tahoe_snow.config import DATA, MODELS, TABLES
from tahoe_snow.snow import phase

RATIO_ROWS = {"fixed 10:1": "Flat 10:1", "Kuchera": "Kuchera (the common free method)",
              "ridge (all)": "This site's trained ratio"}
WATER_ROWS = {"raw": "Raw four-model average", "corrected": "Corrected to the snow sensors (in use)"}
PHASE_ROWS = {"air temperature threshold": "Air-temperature cutoff", "wet-bulb snow level ramp": "Wet-bulb snow level",
              "wet-bulb logistic": "Wet-bulb curve"}


WATER_COLUMNS = ["Method", "Total vs measured", "Daily error (in)", "3-day error (in)",
                 "3-day error, 2 in+ storms (in)"]


def water_section(title: str, note: str, table: str, in_use: str = WATER_ROWS["corrected"]) -> dict | None:
    """Raw against corrected water from a region's held-out storm test, or None where that test is not on hand."""
    path = TABLES / table
    if not path.exists():
        return None
    water = pd.read_csv(path).groupby("method").mean(numeric_only=True)
    labels = {"raw": WATER_ROWS["raw"], "corrected": in_use}
    return {"title": title, "note": note, "columns": WATER_COLUMNS,
            "rows": [[label, f"{100 * water.loc[key, 'total f/o']:.0f}%", f"{water.loc[key, 'daily err in']:.2f}",
                      f"{water.loc[key, '3-day err in']:.2f}", f"{water.loc[key, '3-day 2in+ err']:.2f}"]
                     for key, label in labels.items()]}


def seattle_sections() -> list:
    """Seattle's three tests, each None where its table is not on hand: water against its ten sensors, the rain/snow
    split against the Sierra's on the same days, and the Sierra's snow ratio on Cascade snow days."""
    water = water_section(
        "Water, Seattle.",
        "The same test against 10 snow sensors in the Washington Cascades and Olympics, on the 2024, 2025, and 2026 "
        "winters held out in turn. Crystal Mountain and White Pass use the curve pooled over all ten, which did "
        "better there than their own sensor's. Mt. Rainier, Mt. Baker, and Mt. St. Helens are shown their sensor "
        "but left uncorrected, since it sits far below the mountain; Glacier Peak and Mt. Adams have none.",
        "bias_methods_seattle.csv", "Corrected to the snow sensors (in use, except on the volcanoes)")
    split = ratio = None
    if (TABLES / "phase_table_seattle.csv").exists():
        table = pd.read_csv(TABLES / "phase_table_seattle.csv", index_col=0)
        kind, params = phase.load("seattle")
        sierra = phase.load()[1]
        row = table.loc[kind]
        split = {"title": "Rain or snow, Seattle.",
                 "note": f"The same test at {int(row['stations'])} snow sensors in the Washington Cascades and "
                         f"Olympics over {int(row['days']):,} held-out days, {int(row['mixed days']):,} of them mixed. "
                         f"Seattle's curve is centered at {params['center_c']:g} C of wet-bulb against the Sierra's "
                         f"{sierra['center_c']:g} C: more of each storm is rain. Calling everything snow would miss "
                         f"by {float(row['all_snow_error']):.1f} mm.",
                 "columns": ["Method", "Error (mm of water)", "On mixed days (mm)"],
                 "rows": [["The Sierra's wet-bulb curve", f"{row['sierra_error']:.2f}",
                           f"{row['sierra_mixed_error']:.2f}"],
                          ["Seattle's wet-bulb curve (in use)", f"{row['held-out error (mm water)']:.2f}",
                           f"{row['error on mixed days (mm water)']:.2f}"]]}
    check = MODELS / "snow_ratio_check_seattle.json"
    if check.exists():
        record = json.loads(check.read_text())
        on = record["checked_on"]
        pooled = record["pooled_refit_each_station_held_out"]
        rows = {"flat_10_to_1": RATIO_ROWS["fixed 10:1"], "kuchera": RATIO_ROWS["Kuchera"],
                "sierra_model": "This site's ratio, trained in the Sierra (in use)"}
        ratio = {"title": "Snow ratio, Seattle.",
                 "note": f"The Sierra-trained ratio on {on['days']:,} hand-measured snow days at {on['stations']} "
                         f"Washington stations, {on['first_date'][:4]} to {on['last_date'][:4]}, none of which it "
                         "was trained on. Refitting it with those days added did no better at a station held out "
                         f"({pooled['snow_error_in']:.2f} in), so the Sierra's is kept. It runs a little fluffy west "
                         "of the crest and dense east of it.",
                 "columns": ["Method", "Snowfall error (in)", "Average miss (in)"],
                 "rows": [[label, f"{record[key]['snow_error_in']:.2f}", f"{record[key]['snow_bias_in']:+.2f}"]
                          for key, label in rows.items()]}
    return [("Water, Seattle.", water), ("Rain or snow, Seattle.", split), ("Snow ratio, Seattle.", ratio)]


def scorecard() -> dict:
    """The scorecard, rebuilt from the tests on hand. A section whose test is not on this machine is carried over
    from the scorecard already published, so rebuilding one region's tests does not drop another's."""
    ratio = pd.read_csv(TABLES / "ratio_cv_season.csv", index_col=0)
    in_use = phase.load()[0]
    split = pd.read_csv(TABLES / "phase_table.csv", index_col=0)
    published = DATA / "scorecard.json"
    kept = {s["title"]: s for s in json.loads(published.read_text())["sections"]} if published.exists() else {}
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
        water_section("Water.", "Model water against what 22 snow sensors measured, on the 2025 and 2026 winters "
                                "held out in turn.", "bias_methods.csv"),
    ]
    regional = [("Water, Mammoth area.", water_section(
        "Water, Mammoth area.",
        "The same test against 10 snow sensors along the crest around Mammoth, on the 2024, 2025, and "
        "2026 winters held out in turn. Mammoth Mountain and Sherwin Ridge use the Mammoth Pass sensor, "
        "Matterhorn Peak the Slide Canyon one, and Dana Plateau the Dana Meadows one; June Mountain, "
        "Carson Peak, and Mt. Whitney have no working sensor nearby and are left uncorrected.",
        "bias_methods_mammoth.csv", "Corrected to the snow sensors (in use where a sensor is near)"))]
    regional += seattle_sections()
    sections += [built or kept[title] for title, built in regional if built or title in kept]
    sections += [
        {"title": "Live forecasts.",
         "note": "Every forecast this page shows is archived and will be graded against the stations by lead "
                 "day as it comes due, including the ranges. That table starts filling in after the first week.",
         "columns": [], "rows": []},
    ]
    card = {"sections": sections}
    (DATA / "scorecard.json").write_text(json.dumps(card))
    return card
