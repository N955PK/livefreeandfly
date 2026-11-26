"""The scorecard is rebuilt from the tests on hand and keeps the sections whose tests are somewhere else."""
import json

import pandas as pd

from tahoe_snow import verify

METHODS = pd.DataFrame({"season": [2025, 2025, 2026, 2026], "method": ["raw", "corrected"] * 2,
                        "daily err in": [0.3, 0.2, 0.2, 0.2], "total f/o": [0.7, 1.0, 0.8, 1.02],
                        "1in+ day err": [0.6, 0.5, 0.6, 0.5], "3-day err in": [0.6, 0.4, 0.5, 0.4],
                        "3-day 2in+ err": [1.2, 0.8, 1.4, 0.7]})
MAMMOTH = {"title": "Water, Mammoth area.", "note": "kept", "columns": ["Method"], "rows": [["as published"]]}


def tables(folder, seattle: bool):
    pd.DataFrame({"n": [10] * 3, "snow_mae_in": [2.0, 2.1, 1.6], "snow_bias_in": [-0.7, 0.5, 0.0]},
                 index=list(verify.RATIO_ROWS)).to_csv(folder / "ratio_cv_season.csv")
    split = pd.DataFrame({"days": 100, "held-out error (mm water)": [2.5, 2.4, 2.4],
                          "error on mixed days (mm water)": [6.1, 5.8, 5.8], "mixed days": 30, "all_snow_error": 4.9,
                          "sierra_error": 3.27, "sierra_mixed_error": 6.16, "stations": 64},
                         index=list(verify.PHASE_ROWS))
    split.to_csv(folder / "phase_table.csv")
    METHODS.to_csv(folder / "bias_methods.csv", index=False)
    if seattle:
        split.to_csv(folder / "phase_table_seattle.csv")
        METHODS.to_csv(folder / "bias_methods_seattle.csv", index=False)


def test_a_water_section_averages_the_held_out_winters(tmp_path, monkeypatch):
    monkeypatch.setattr(verify, "TABLES", tmp_path)
    tables(tmp_path, seattle=True)
    section = verify.water_section("Water, Cascades.", "note", "bias_methods_seattle.csv", "Corrected (in use)")
    assert section["rows"] == [["Raw four-model average", "75%", "0.25", "0.55", "1.30"],
                               ["Corrected (in use)", "101%", "0.20", "0.40", "0.75"]]
    assert verify.water_section("Water, Nowhere.", "note", "bias_methods_nowhere.csv") is None


def test_seattle_has_its_three_sections_and_mammoths_is_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(verify, "TABLES", tmp_path)
    monkeypatch.setattr(verify, "DATA", tmp_path)
    tables(tmp_path, seattle=True)
    (tmp_path / "scorecard.json").write_text(json.dumps({"sections": [MAMMOTH]}))
    card = verify.scorecard()
    assert [s["title"] for s in card["sections"]] == [
        "Snow ratio.", "Rain or snow.", "Water.", "Water, Mammoth area.", "Water, Cascades.",
        "Rain or snow, Cascades.", "Snow ratio, Cascades.", "Snow ratio, Tetons.", "Snow ratio, Wasatch.",
        "Snow ratio, Colorado.", "Snow ratio, Montana.", "Snow ratio, Sun Valley.", "Snow ratio, Oregon.",
        "Snow ratio, New Mexico.", "Snow ratio, Alaska.", "Snow ratio, Southwest Colorado.",
        "Snow ratio, Inland Northwest.", "Snow ratio, Northwest Montana.", "Snow ratio, Western Idaho.",
        "Snow ratio, Wyoming.", "Snow ratio, Southern Utah.", "Snow ratio, Arizona.", "Snow ratio, Las Vegas.",
        "Live forecasts."]
    # The Tetons', the Wasatch's and Colorado's water and rain-or-snow tables are not among these; their ratio
    # checks are kept beside the models.
    for at, where in ((-17, "Teton"), (-16, "Wasatch"), (-15, "Colorado"), (-14, "Montana"), (-10, "Alaska"),
                      (-9, "southwest Colorado"), (-4, "southern Utah"), (-3, "Arizona")):
        assert card["sections"][at]["rows"][-1][0] == f"Trained on Sierra and {where} days together (in use)"
    assert json.loads((tmp_path / "scorecard.json").read_text()) == card
    by_title = {s["title"]: s for s in card["sections"]}
    assert by_title["Water, Mammoth area."] == MAMMOTH
    split = by_title["Rain or snow, Cascades."]
    assert split["rows"][0][:2] == ["The Sierra's wet-bulb curve", "3.27"] and "(in use)" in split["rows"][1][0]
    assert "0.75 C" in split["note"] and "1.25 C" in split["note"]
    ratio = by_title["Snow ratio, Cascades."]
    assert ratio["rows"][-1][0].endswith("(in use)") and ratio["rows"][-1][1] < ratio["rows"][0][1]


def test_a_region_with_no_test_on_hand_and_none_published_has_no_section(tmp_path, monkeypatch):
    monkeypatch.setattr(verify, "TABLES", tmp_path)
    monkeypatch.setattr(verify, "DATA", tmp_path)
    tables(tmp_path, seattle=False)
    titles = [s["title"] for s in verify.scorecard()["sections"]]
    assert "Water, Mammoth area." not in titles and "Water, Cascades." not in titles
    assert "Rain or snow, Cascades." not in titles and titles[-1] == "Live forecasts."


def test_a_western_canadian_region_has_a_water_and_a_rain_or_snow_section_and_no_ratio_one(tmp_path, monkeypatch):
    monkeypatch.setattr(verify, "TABLES", tmp_path)
    tables(tmp_path, seattle=False)
    METHODS.to_csv(tmp_path / "bias_methods_eastkootenays.csv", index=False)
    pd.read_csv(tmp_path / "phase_table.csv", index_col=0).to_csv(tmp_path / "phase_table_eastkootenays.csv")
    built = dict(verify.canada_sections())
    assert list(built) == [f"{kind}, {name}." for name in ("Okanagan", "BC Coast", "Powder Highway", "East Kootenays",
                                                           "Canadian Rockies") for kind in ("Water", "Rain or snow")]
    assert built["Water, Okanagan."] is None and built["Rain or snow, Canadian Rockies."] is None
    water = built["Water, East Kootenays."]
    assert water["rows"][1][1] == "101%" and "Fernie" in water["note"]
    assert built["Rain or snow, East Kootenays."]["rows"][1][0] == "The East Kootenays' wet-bulb curve (in use)"
