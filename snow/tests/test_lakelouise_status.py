from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import lakelouise

# The report as the resort's status page read it on 2026-11-24, whole.
PAGE = (Path(__file__).parent / "fixtures" / "lakelouise_status.xml").read_text()
NOW = datetime(2026, 11, 24, 23, 40, tzinfo=timezone.utc)


def page(old: str, new: str, count: int = -1) -> str:
    assert old in PAGE
    return PAGE.replace(old, new, count)


def test_the_early_season_mountain_reads_its_lifts_and_runs_by_area():
    # Lake Louise on 2026-11-24: 4 of 13 lifts and 6 of 171 runs open, all on the Front Side.
    feed = lakelouise.parse(PAGE, NOW)
    assert feed["Name"] == "Lake Louise" and feed["LastUpdate"] == "2026-11-24T23:40:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Front Side", 9, 60), ("Back Bowls", 2, 75), ("Larch", 1, 14), ("Richardson's Ridge", 1, 5),
        ("West Bowl", 0, 17)]
    lifts = {lift["Name"]: lift for area in feed["MountainAreas"] for lift in area["Lifts"]}
    assert lifts["Grizzly Gondola"] == {"Name": "Grizzly Gondola", "Status": "Open", "StatusEnglish": "open",
                                        "Difficulty": None}
    assert sorted(name for name, lift in lifts.items() if lift["StatusEnglish"] == "open") == [
        "Glacier Express", "Grizzly Gondola", "Juniper Express", "Magic Carpet"]
    assert lifts["Larch Express"]["Status"] == "Closed"
    trails = {trail["Name"]: trail for area in feed["MountainAreas"] for trail in area["Trails"]}
    assert len(trails) == 171
    assert trails["Lower Flight"] == {"Name": "Lower Flight", "Status": "Open", "StatusEnglish": "open",
                                      "Difficulty": "Blue", "Grooming": "Yes"}
    assert trails["Deer Run"]["Grooming"] == "No" and trails["Deer Run"]["Difficulty"] == "Green"
    assert trails["Men's Downhill"] == {"Name": "Men's Downhill", "Status": "Closed", "StatusEnglish": "closed",
                                        "Difficulty": "Black", "Grooming": "No"}
    assert {trail["Difficulty"] for trail in trails.values()} == {"Green", "Blue", "Black", "Double black"}
    # The parks and the dining are not runs.
    assert "Sunny Tube Park" not in trails and "Terrain Park" not in trails


def test_the_snow_report_is_in_inches_from_the_report_s_centimetres():
    snow = lakelouise.parse(PAGE, NOW)["SnowReport"]
    # "2026-11-24T15:04:52-06:00": Alberta keeps one time all year, six hours behind UTC.
    assert snow["LastUpdate"] == "2026-11-24T21:04:52Z" and snow["Resortwide"] is False
    # 25 cm of base and 5 cm in 24 hours low down, 30 cm and 6 cm up high, 50 cm this season; the middle is empty.
    assert snow["BaseArea"] == {"Name": "Lower Mountain", "BaseIn": 9.8, "OvernightIn": 0.0, "Last24HoursIn": 2.0,
                                "Last48HoursIn": 2.0, "Last7DaysIn": 2.0}
    assert snow["SummitArea"] == {"Name": "Upper Mountain", "BaseIn": 11.8, "OvernightIn": 0.0,
                                  "Last24HoursIn": 2.4, "Last48HoursIn": 2.4, "Last7DaysIn": 2.4}
    assert "MidMountainArea" not in snow and snow["SeasonTotalIn"] == 19.7 and snow["BaseConditions"] is None
    said = lakelouise.parse(page("name=\"Upper Mountain\" primarySurface=\"\"",
                                 "name=\"Upper Mountain\" primarySurface=\"Packed Powder\""), NOW)["SnowReport"]
    assert said["BaseConditions"] == "Packed Powder"


def test_a_report_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="Grizzly Gondola has a status the reader does not know: 'Standby'"):
        lakelouise.parse(page("name=\"Grizzly Gondola\" status=\"Open\"", "name=\"Grizzly Gondola\" status=\"Standby\""),
                         NOW)
    with pytest.raises(ValueError, match="Deer Run has a difficulty the reader does not know: 'novice'"):
        lakelouise.parse(page("name=\"Deer Run\" status=\"Open\" groomed=\"no\" realtime=\"Closed\" "
                              "difficulty=\"beginner\"",
                              "name=\"Deer Run\" status=\"Open\" groomed=\"no\" realtime=\"Closed\" "
                              "difficulty=\"novice\""), NOW)
    with pytest.raises(ValueError, match="Deer Run has a grooming the reader does not know: 'partly'"):
        lakelouise.parse(page("name=\"Deer Run\" status=\"Open\" groomed=\"no\"",
                              "name=\"Deer Run\" status=\"Open\" groomed=\"partly\""), NOW)
    with pytest.raises(ValueError, match="counts 5 open lifts but 4 of 13"):
        lakelouise.parse(page("runs=\"6\" lifts=\"4\"", "runs=\"6\" lifts=\"5\""), NOW)
    with pytest.raises(ValueError, match="counts 6 open runs but 5 of 171"):
        lakelouise.parse(page("name=\"Deer Run\" status=\"Open\"", "name=\"Deer Run\" status=\"Closed\""), NOW)
    with pytest.raises(ValueError, match="does not read as XML"):
        lakelouise.parse("<!doctype html><html><body><div id=root></div></body></html>", NOW)
    with pytest.raises(ValueError, match="not the mountain's report"):
        lakelouise.parse("<html><body/></html>", NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    for old, new in (("units=\"metric\"", "units=\"imperial\""), ("base=\"30\"", "base=\"deep\""),
                     ("lastSnowfallUpdate=\"2026-11-24T15:04:52-06:00\"", "lastSnowfallUpdate=\"this morning\""),
                     ("lastSnowfallUpdate=\"2026-11-24T15:04:52-06:00\"", "lastSnowfallUpdate=\"2026-11-24T15:04:52\""),
                     ("location name=\"Upper Mountain\"", "location name=\"Summit\"")):
        feed = lakelouise.parse(page(old, new), NOW)
        assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 5
