import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import jacksonhole

PAGE = (Path(__file__).parent / "fixtures" / "jacksonhole.json").read_text()
NOW = datetime(2026, 11, 24, 18, 0, tzinfo=timezone.utc)


def changed(**parts) -> str:
    report = json.loads(PAGE)
    for path, value in parts.items():
        *keys, last = path.split("__")
        at = report
        for key in keys:
            at = at[key]
        at[last] = value
    return json.dumps(report)


def test_the_mountain_before_opening_reads_as_every_lift_and_trail_closed():
    # Jackson Hole's report on 2026-11-24, three days before it opened: 13 lifts and 145 trails.
    feed = jacksonhole.parse(PAGE, NOW)
    assert feed["Name"] == "Jackson Hole" and feed["LastUpdate"] == "2026-11-24T18:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Jackson Hole", 13, 145)]
    area = feed["MountainAreas"][0]
    assert [lift["Name"] for lift in area["Lifts"]][:3] == ["Aerial Tram", "Apres Vous Quad", "Bridger Gondola"]
    # "Out of period" (shut for the season) is said as closed.
    assert {row["StatusEnglish"] for row in area["Lifts"] + area["Trails"]} == {"closed"}
    trails = {trail["Name"]: trail for trail in area["Trails"]}
    assert trails["Alta Chute 1"] == {"Name": "Alta Chute 1", "Status": "Closed", "StatusEnglish": "closed",
                                      "Difficulty": "Double black", "Grooming": "No"}
    # A double blue is a blue, and a trail the report marks groomed is groomed.
    assert trails["Hanging Rock"]["Difficulty"] == "Blue" and trails["Hanging Rock"]["Grooming"] == "Yes"
    assert trails["Eagle's Rest"]["Difficulty"] == "Green"
    assert sum(trail["Difficulty"] == "" for trail in area["Trails"]) == 4          # the terrain parks


def test_the_snow_report_is_the_mid_mountain_and_tram_summit_plots_with_nothing_for_the_base():
    snow = jacksonhole.parse(PAGE, NOW)["SnowReport"]
    assert snow["LastUpdate"] == "2026-11-24T17:19:00Z" and snow["Resortwide"] is False
    assert "BaseArea" not in snow and snow["SeasonTotalIn"] == 23 and snow["Alert"] is None
    assert snow["MidMountainArea"] == {"Name": "Mid-Mountain", "BaseIn": 10, "Last24HoursIn": 1, "Last48HoursIn": 1,
                                       "Last72HoursIn": None, "Last7DaysIn": None, "SeasonTotalIn": 23}
    assert snow["SummitArea"]["BaseIn"] == 24 and snow["SummitArea"]["Last7DaysIn"] == 30
    assert snow["Report"].startswith("November 19, 2026")


def test_an_open_lift_and_one_on_hold_take_the_report_s_words():
    feed = jacksonhole.parse(changed(lifts__aerialTram__openingStatus="OPEN",
                                     lifts__bridgerGondola__openingStatus="WIND_HOLD"), NOW)
    lifts = {lift["Name"]: lift for lift in feed["MountainAreas"][0]["Lifts"]}
    assert (lifts["Aerial Tram"]["Status"], lifts["Aerial Tram"]["StatusEnglish"]) == ("Open", "open")
    assert (lifts["Bridger Gondola"]["Status"], lifts["Bridger Gondola"]["StatusEnglish"]) == ("Wind hold", "wind hold")


def test_a_report_whose_lifts_do_not_match_its_count_or_whose_levels_are_new_is_refused():
    with pytest.raises(ValueError, match="counts 14 lifts but 13"):
        jacksonhole.parse(changed(liftStatus__totalLifts=14), NOW)
    with pytest.raises(ValueError, match="counts 200 trails but only 145"):
        jacksonhole.parse(changed(trailStatus__totalTrails=200), NOW)
    with pytest.raises(ValueError, match="a level the reader does not know"):
        jacksonhole.parse(changed(trails__nezPerce__trailLevel="ORANGE_OVAL"), NOW)


def test_a_snow_figure_not_in_inches_costs_the_snow_report_and_not_the_lifts(capsys):
    feed = jacksonhole.parse(changed(snow__midMountain__totalSnowDepth__unit="CENTIMETER"), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"][0]["Lifts"]) == 13
    assert "snow report" in capsys.readouterr().out
