"""Scorecard for the site, assembled from the held-out tests saved while fitting."""
import json

import pandas as pd

from tahoe_snow import config
from tahoe_snow.config import ALL_RESORTS, DATA, MODELS, TABLES
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
        "Water, Washington Cascades.",
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
        split = {"title": "Rain or snow, Washington Cascades.",
                 "note": f"The same test at {int(row['stations'])} snow sensors in the Washington Cascades and "
                         f"Olympics over {int(row['days']):,} held-out days, {int(row['mixed days']):,} of them mixed. "
                         f"The Cascades' curve is centered at {params['center_c']:g} C of wet-bulb against the Sierra's "
                         f"{sierra['center_c']:g} C: more of each storm is rain. Calling everything snow would miss "
                         f"by {float(row['all_snow_error']):.1f} mm.",
                 "columns": ["Method", "Error (mm of water)", "On mixed days (mm)"],
                 "rows": [["The Sierra's wet-bulb curve", f"{row['sierra_error']:.2f}",
                           f"{row['sierra_mixed_error']:.2f}"],
                          ["The Cascades' wet-bulb curve (in use)", f"{row['held-out error (mm water)']:.2f}",
                           f"{row['error on mixed days (mm water)']:.2f}"]]}
    check = MODELS / "snow_ratio_check_seattle.json"
    if check.exists():
        record = json.loads(check.read_text())
        on = record["checked_on"]
        pooled = record["pooled_refit_each_station_held_out"]
        rows = {"flat_10_to_1": RATIO_ROWS["fixed 10:1"], "kuchera": RATIO_ROWS["Kuchera"],
                "sierra_model": "This site's ratio, trained in the Sierra (in use)"}
        ratio = {"title": "Snow ratio, Washington Cascades.",
                 "note": f"The Sierra-trained ratio on {on['days']:,} hand-measured snow days at {on['stations']} "
                         f"Washington stations, {on['first_date'][:4]} to {on['last_date'][:4]}, none of which it "
                         "was trained on. Refitting it with those days added did no better at a station held out "
                         f"({pooled['snow_error_in']:.2f} in), so the Sierra's is kept. It runs a little fluffy west "
                         "of the crest and dense east of it.",
                 "columns": ["Method", "Snowfall error (in)", "Average miss (in)"],
                 "rows": [[label, f"{record[key]['snow_error_in']:.2f}", f"{record[key]['snow_bias_in']:+.2f}"]
                          for key, label in rows.items()]}
    return [("Water, Washington Cascades.", water), ("Rain or snow, Washington Cascades.", split), ("Snow ratio, Washington Cascades.", ratio)]


def tetons_sections() -> list:
    """The Tetons' three tests, each None where its table is not on hand: water against ten sensors, the rain/snow
    split against the Sierra's on the same days, and the snow ratio on Teton snow days."""
    water = water_section(
        "Water, Tetons.",
        "The same test against 10 snow sensors from the Snake River's headwaters to the Gros Ventre, on the 2024, "
        "2025, and 2026 winters held out in turn. Grand Targhee and Togwotee Pass use their own sensor and Jackson "
        "Hole and Teton Pass the Phillips Bench one; Snow King has none within reach and is left uncorrected.",
        "bias_methods_tetons.csv", "Corrected to the snow sensors (in use where a sensor is near)")
    split = ratio = None
    if (TABLES / "phase_table_tetons.csv").exists():
        table = pd.read_csv(TABLES / "phase_table_tetons.csv", index_col=0)
        kind, params = phase.load("tetons")
        row = table.loc[kind]
        split = {"title": "Rain or snow, Tetons.",
                 "note": f"The same test at {int(row['stations'])} snow sensors around the Tetons over "
                         f"{int(row['days']):,} held-out days, {int(row['mixed days']):,} of them mixed. Nearly all "
                         f"of it is snow there: calling everything snow would miss by only "
                         f"{float(row['all_snow_error']):.1f} mm. The curve fitted there is centered at "
                         f"{params['center_c']:g} C of wet-bulb and does no better than the Sierra's.",
                 "columns": ["Method", "Error (mm of water)", "On mixed days (mm)"],
                 "rows": [["The Sierra's wet-bulb curve", f"{row['sierra_error']:.2f}",
                           f"{row['sierra_mixed_error']:.2f}"],
                          ["The Tetons' wet-bulb curve (in use)", f"{row['held-out error (mm water)']:.2f}",
                           f"{row['error on mixed days (mm water)']:.2f}"]]}
    check = MODELS / "snow_ratio_check_tetons.json"
    if check.exists():
        record = json.loads(check.read_text())
        on = record["checked_on"]
        rows = {"flat_10_to_1": RATIO_ROWS["fixed 10:1"], "kuchera": RATIO_ROWS["Kuchera"],
                "sierra_model": "This site's ratio, trained in the Sierra",
                "pooled_refit_each_station_held_out": "Trained on Sierra and Teton days together (in use)"}
        ratio = {"title": "Snow ratio, Tetons.",
                 "note": f"{on['days']:,} hand-measured snow days at {on['stations']} stations around Jackson, "
                         f"{on['first_date'][:4]} to {on['last_date'][:4]}, where the snow averages 14 to 1. The "
                         "Sierra-trained ratio already reads that from the cold, so adding the Teton days changes "
                         "little; the one in use is scored here at stations it never saw.",
                 "columns": ["Method", "Snowfall error (in)", "Average miss (in)"],
                 "rows": [[label, f"{record[key]['snow_error_in']:.2f}", f"{record[key]['snow_bias_in']:+.2f}"]
                          for key, label in rows.items()]}
    return [("Water, Tetons.", water), ("Rain or snow, Tetons.", split), ("Snow ratio, Tetons.", ratio)]


def wasatch_sections() -> list:
    """The Wasatch's three tests, each None where its table is not on hand: water against ten sensors, the
    rain/snow split against the Sierra's on the same days, and the snow ratio on Wasatch snow days."""
    water = water_section(
        "Water, Wasatch.",
        "The same test against 10 snow sensors from Timpanogos Divide to Ben Lomond Peak, on the 2024, 2025, and "
        "2026 winters held out in turn. The models are driest in Little Cottonwood, where they deliver under half "
        "of what Snowbird's sensor measures. Snowbasin has no sensor within reach and is left uncorrected.",
        "bias_methods_wasatch.csv", "Corrected to the snow sensors (in use where a sensor is near)")
    split = ratio = None
    if (TABLES / "phase_table_wasatch.csv").exists():
        table = pd.read_csv(TABLES / "phase_table_wasatch.csv", index_col=0)
        kind, params = phase.load("wasatch")
        row = table.loc[kind]
        split = {"title": "Rain or snow, Wasatch.",
                 "note": f"The same test at {int(row['stations'])} snow sensors in the Wasatch over "
                         f"{int(row['days']):,} held-out days, {int(row['mixed days']):,} of them mixed; calling "
                         f"everything snow would miss by {float(row['all_snow_error']):.1f} mm. The curve fitted "
                         f"there is centered at {params['center_c']:g} C of wet-bulb, lower than the Sierra's "
                         f"{phase.load()[1]['center_c']:g} C.",
                 "columns": ["Method", "Error (mm of water)", "On mixed days (mm)"],
                 "rows": [["The Sierra's wet-bulb curve", f"{row['sierra_error']:.2f}",
                           f"{row['sierra_mixed_error']:.2f}"],
                          ["The Wasatch's wet-bulb curve (in use)", f"{row['held-out error (mm water)']:.2f}",
                           f"{row['error on mixed days (mm water)']:.2f}"]]}
    check = MODELS / "snow_ratio_check_wasatch.json"
    if check.exists():
        record = json.loads(check.read_text())
        on = record["checked_on"]
        rows = {"flat_10_to_1": RATIO_ROWS["fixed 10:1"], "kuchera": RATIO_ROWS["Kuchera"],
                "sierra_model": "This site's ratio, trained in the Sierra",
                "pooled_refit_each_station_held_out": "Trained on Sierra and Wasatch days together (in use)"}
        ratio = {"title": "Snow ratio, Wasatch.",
                 "note": f"{on['days']:,} hand-measured snow days at {on['stations']} stations from Alta and "
                         f"Brighton down to the benches, {on['first_date'][:4]} to {on['last_date'][:4]}, where the "
                         "snow averages 12 to 1. The Sierra-trained ratio runs an inch too deep on them, so the one "
                         "in use is trained on both, with a Wasatch day counted ten times; it is scored here at "
                         "stations it never saw.",
                 "columns": ["Method", "Snowfall error (in)", "Average miss (in)"],
                 "rows": [[label, f"{record[key]['snow_error_in']:.2f}", f"{record[key]['snow_bias_in']:+.2f}"]
                          for key, label in rows.items()]}
    return [("Water, Wasatch.", water), ("Rain or snow, Wasatch.", split), ("Snow ratio, Wasatch.", ratio)]


def colorado_sections() -> list:
    """Colorado's three tests, each None where its table is not on hand: water against sixteen sensors, the
    rain/snow split against the Sierra's on the same days, and the snow ratio on Colorado snow days."""
    water = water_section(
        "Water, Northern Colorado.",
        "The same test against 16 snow sensors, twelve along I-70 from Beaver Creek to Berthoud Pass and four in "
        "the Park Range above Steamboat, on the 2024, 2025, and 2026 winters held out in turn. The models are "
        "driest above Steamboat, where they deliver under half of what the Tower sensor measures. Breckenridge has "
        "no sensor within reach and is left uncorrected.",
        "bias_methods_colorado.csv", "Corrected to the snow sensors (in use where a sensor is near)")
    split = ratio = None
    if (TABLES / "phase_table_colorado.csv").exists():
        table = pd.read_csv(TABLES / "phase_table_colorado.csv", index_col=0)
        kind, params = phase.load("colorado")
        row = table.loc[kind]
        split = {"title": "Rain or snow, Northern Colorado.",
                 "note": f"The same test at {int(row['stations'])} snow sensors in Colorado over "
                         f"{int(row['days']):,} held-out days, {int(row['mixed days']):,} of them mixed. Nearly all "
                         f"of it is snow there: calling everything snow would miss by only "
                         f"{float(row['all_snow_error']):.1f} mm. The curve fitted there is centered at "
                         f"{params['center_c']:g} C of wet-bulb and does little better than the Sierra's.",
                 "columns": ["Method", "Error (mm of water)", "On mixed days (mm)"],
                 "rows": [["The Sierra's wet-bulb curve", f"{row['sierra_error']:.2f}",
                           f"{row['sierra_mixed_error']:.2f}"],
                          ["Colorado's wet-bulb curve (in use)", f"{row['held-out error (mm water)']:.2f}",
                           f"{row['error on mixed days (mm water)']:.2f}"]]}
    check = MODELS / "snow_ratio_check_colorado.json"
    if check.exists():
        record = json.loads(check.read_text())
        on = record["checked_on"]
        rows = {"flat_10_to_1": RATIO_ROWS["fixed 10:1"], "kuchera": RATIO_ROWS["Kuchera"],
                "sierra_model": "This site's ratio, trained in the Sierra",
                "pooled_refit_each_station_held_out": "Trained on Sierra and Colorado days together (in use)"}
        ratio = {"title": "Snow ratio, Northern Colorado.",
                 "note": f"{on['days']:,} hand-measured snow days at {on['stations']} stations from Climax and "
                         f"Breckenridge to Steamboat Springs, {on['first_date'][:4]} to {on['last_date'][:4]}, "
                         "where the snow averages nearly 15 to 1. The Sierra-trained ratio runs half an inch deep "
                         "on them, so the one in use is trained on both; it is scored here at stations it never "
                         "saw.",
                 "columns": ["Method", "Snowfall error (in)", "Average miss (in)"],
                 "rows": [[label, f"{record[key]['snow_error_in']:.2f}", f"{record[key]['snow_bias_in']:+.2f}"]
                          for key, label in rows.items()]}
    return [("Water, Northern Colorado.", water), ("Rain or snow, Northern Colorado.", split), ("Snow ratio, Northern Colorado.", ratio)]


# Canada's western regions: the name each goes by, then what its water test was run against and which mountains the
# correction reaches.
CANADA = {
    "okanagan": ("Okanagan", "the Okanagan",
                 "10 snow stations in the Okanagan highlands. The models deliver about half of what the stations "
                 "measure, and a third of it at Silver Star Mountain. SilverStar is corrected against that station; "
                 "Big White, Sun Peaks and Apex have none within reach and are left uncorrected."),
    "bccoast": ("BC South Coast", "the south Coast Mountains",
                "11 snow stations from the North Shore to Bralorne and Vancouver Island. The models are closer here, "
                "but deliver 70% of what Palisade Lake measures above Grouse, which is corrected against it. Nothing "
                "with a record is within reach of Whistler, Cypress, Mt. Seymour or Mt. Washington, which are left "
                "uncorrected."),
    "powderhighway": ("Powder Highway", "the Selkirks and Monashees",
                      "9 snow stations in the Selkirks and Monashees. Revelstoke is corrected against Mount "
                      "Revelstoke's station, where the models deliver 56%, and Rogers Pass against the station in "
                      "the valley below it; RED Mountain, Whitewater and Kootenay Pass have none within reach and "
                      "are left uncorrected."),
    "eastkootenays": ("East Kootenays", "the Purcells and the Rockies' west slope",
                      "6 snow stations in the Purcells and on the Rockies' west slope. Fernie is corrected against "
                      "Morrissey Ridge; Kicking Horse, Panorama and Kimberley have no station within reach and are "
                      "left uncorrected."),
    "rockies": ("Banff & Jasper", "the Rockies and the Columbias beside them",
                "4 snow stations on the British Columbia side of the divide, which is all that has a record: Alberta "
                "publishes five days of readings. Bow Summit is corrected against Wildcat Creek; the mountains in "
                "Alberta are left uncorrected."),
}


def canada_sections() -> list:
    """Each western Canadian region's two tests, each None where its table is not on hand: water against British
    Columbia's snow stations, and the rain/snow split against the Sierra's on the same days. There is no snow
    ratio test: Canada's climate stations report snowfall as ten times its water."""
    out = []
    for region, (name, where, stations) in CANADA.items():
        water = water_section(
            f"Water, {name}.",
            f"The same test against {stations} The 2024, 2025, and 2026 winters are held out in turn.",
            f"bias_methods_{region}.csv", "Corrected to the snow stations (in use where a station is near)")
        split = None
        if (TABLES / f"phase_table_{region}.csv").exists():
            table = pd.read_csv(TABLES / f"phase_table_{region}.csv", index_col=0)
            kind, params = phase.load(region)
            row = table.loc[kind]
            split = {"title": f"Rain or snow, {name}.",
                     "note": f"The same test at {int(row['stations'])} snow stations in {where} over "
                             f"{int(row['days']):,} held-out days, {int(row['mixed days']):,} of them mixed; calling "
                             f"everything snow would miss by {float(row['all_snow_error']):.1f} mm. The curve fitted "
                             f"there is centered at {params['center_c']:g} C of wet-bulb, against the Sierra's "
                             f"{phase.load()[1]['center_c']:g} C.",
                     "columns": ["Method", "Error (mm of water)", "On mixed days (mm)"],
                     "rows": [["The Sierra's wet-bulb curve", f"{row['sierra_error']:.2f}",
                               f"{row['sierra_mixed_error']:.2f}"],
                              [f"The {name}'{'' if name.endswith('s') else 's'} wet-bulb curve (in use)",
                               f"{row['held-out error (mm water)']:.2f}",
                               f"{row['error on mixed days (mm water)']:.2f}"]]}
        out += [(f"Water, {name}.", water), (f"Rain or snow, {name}.", split)]
    return out


# The third collector's regions: the name each goes by, where its sensors are, and what its snow days are called.
WEST = {
    "montana": ("Southwest Montana", "southwest Montana, from the Little Belts to the Beartooths", "Montana"),
    "sunvalley": ("Sun Valley", "the Sawtooths and the mountains around Sun Valley", "Idaho"),
    "oregon": ("Oregon Cascades", "Oregon's Cascades, from Mt. Hood to Willamette Pass", "Oregon"),
    "newmexico": ("New Mexico", "the Sangre de Cristo and Jemez mountains", "New Mexico"),
    "alaska": ("Anchorage", "the Chugach, the Kenai and the Talkeetna mountains", "Alaska"),
    "swcolorado": ("Southwest Colorado", "the Elk Mountains, the Sawatch and the San Juans", "southwest Colorado"),
    # The fourth collector's regions that have sensors.
    "inlandnw": ("Inland Northwest", "the Selkirks, the Silver Valley and the hills north of Spokane", "Inland Northwest"),
    "nwmontana": ("Northwest Montana", "northwest Montana, from the Whitefish Range to the Bitterroot", "Montana"),
    "westidaho": ("Western Idaho", "the mountains around McCall and Boise and Oregon's Elkhorns", "Idaho"),
    "wyoming": ("Wyoming", "Wyoming's ranges outside Jackson", "Wyoming"),
    "southutah": ("Southwest Utah", "the Tushars and the Markagunt Plateau", "southern Utah"),
    "arizona": ("Arizona", "the San Francisco Peaks and the White Mountains", "Arizona"),
    "lasvegas": ("Las Vegas", "the Spring Mountains", "Nevada"),
}


def west_stations(region: str) -> dict:
    """A region's sensors: the first six regions' own tables, the later ones' shared one."""
    return config.MORE_STATIONS.get(region) or getattr(config, f"{region.upper()}_STATIONS")


def _listed(names: list) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def west_reach(region: str) -> str:
    """Which of a region's mountains the correction does not reach, read from the configuration."""
    mountains = [r for r in ALL_RESORTS.values() if r.region == region]
    shown = [r.name for r in mountains if r.station and not r.corrected]
    bare = [r.name for r in mountains if not r.station]
    said = []
    if shown:
        said.append(f"{_listed(shown)} {'is' if len(shown) == 1 else 'are'} shown a sensor but left uncorrected, "
                    "since it sits far below the mountain")
    if bare:
        said.append(f"{_listed(bare)} {'has' if len(bare) == 1 else 'have'} no sensor within reach and "
                    f"{'is' if len(bare) == 1 else 'are'} left uncorrected")
    return ("; ".join(said) + ".") if said else "Every mountain there has a sensor within reach."


def west_sections() -> list:
    """Each of the third collector's regions' three tests, each None where its table is not on hand: water against
    its snow sensors, the rain/snow split against the Sierra's on the same days, and the snow ratio on the
    region's hand-measured snow days."""
    out = []
    for region, (name, where, people) in WEST.items():
        reach = west_reach(region)
        water = water_section(
            f"Water, {name}.",
            f"The same test against {len(west_stations(region))} snow sensors in {where}, on the 2024, 2025, "
            f"and 2026 winters held out in turn. {reach[0].upper() + reach[1:]}",
            f"bias_methods_{region}.csv", "Corrected to the snow sensors (in use where a sensor is near)")
        split = ratio = None
        if (TABLES / f"phase_table_{region}.csv").exists():
            table = pd.read_csv(TABLES / f"phase_table_{region}.csv", index_col=0)
            kind, params = phase.load(region)
            row = table.loc[kind]
            split = {"title": f"Rain or snow, {name}.",
                     "note": f"The same test at {int(row['stations'])} snow sensors in {where} over "
                             f"{int(row['days']):,} held-out days, {int(row['mixed days']):,} of them mixed; calling "
                             f"everything snow would miss by {float(row['all_snow_error']):.1f} mm. The curve fitted "
                             f"there is centered at {params['center_c']:g} C of wet-bulb, against the Sierra's "
                             f"{phase.load()[1]['center_c']:g} C.",
                     "columns": ["Method", "Error (mm of water)", "On mixed days (mm)"],
                     "rows": [["The Sierra's wet-bulb curve", f"{row['sierra_error']:.2f}",
                               f"{row['sierra_mixed_error']:.2f}"],
                              [f"{name}'s wet-bulb curve (in use)", f"{row['held-out error (mm water)']:.2f}",
                               f"{row['error on mixed days (mm water)']:.2f}"]]}
        check = MODELS / f"snow_ratio_check_{region}.json"
        if check.exists():
            record = json.loads(check.read_text())
            on = record["checked_on"]
            own = (MODELS / f"snow_ratio_{region}.json").exists()
            rows = {"flat_10_to_1": RATIO_ROWS["fixed 10:1"], "kuchera": RATIO_ROWS["Kuchera"],
                    "sierra_model": "This site's ratio, trained in the Sierra" + ("" if own else " (in use)"),
                    "pooled_refit_each_station_held_out":
                        f"Trained on Sierra and {people} days together" + (" (in use)" if own else "")}
            ratio = {"title": f"Snow ratio, {name}.",
                     "note": f"{on['days']:,} hand-measured snow days at {on['stations']} stations in {where}, "
                             f"{on['first_date'][:4]} to {on['last_date'][:4]}. The ratio trained on both is scored "
                             "at stations it never saw; "
                             + ("it did better there than the Sierra's alone and is the one in use."
                                if own else "it did no better there than the Sierra's alone, which stays in use."),
                     "columns": ["Method", "Snowfall error (in)", "Average miss (in)"],
                     "rows": [[label, f"{record[key]['snow_error_in']:.2f}", f"{record[key]['snow_bias_in']:+.2f}"]
                              for key, label in rows.items()]}
        out += [(f"Water, {name}.", water), (f"Rain or snow, {name}.", split), (f"Snow ratio, {name}.", ratio)]
    return out


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
    regional += seattle_sections() + tetons_sections() + wasatch_sections() + colorado_sections()
    regional += canada_sections()
    regional += west_sections()
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
