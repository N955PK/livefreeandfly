from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import skibigbear

# The whole page as the site sent it.
PAGE = (Path(__file__).parent / "fixtures" / "skibigbear.html").read_text()
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)
DEPTH = '{"key":"Base Depth","value":"N/A"}'
SURFACE = '{"key":"Snow Surface","value":"N/A"}'


def changed(old: str, new: str, page: str = PAGE) -> str:
    assert old in page
    return page.replace(old, new)


def test_the_closed_mountain_reads_its_lifts_and_the_trails_of_each_difficulty():
    # Ski Big Bear's page on 2026-11-26, last updated when it closed in March: seven lifts and 18 trails, all closed.
    feed = skibigbear.parse(PAGE, NOW)
    assert feed["Name"] == "Ski Big Bear" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Ski Big Bear", 7, 0), ("Beginner Trails", 0, 6), ("Intermediate Trails", 0, 6), ("Advanced Trails", 0, 5),
        ("Expert Trails", 0, 1)]
    lifts = feed["MountainAreas"][0]["Lifts"]
    assert [lift["Name"] for lift in lifts] == [
        "Thundercloud Chair 1", "Thundercloud Chair 2", "Little Bear Chair", "Grizzly Chair", "Magic Carpet 1",
        "Magic Carpet 2", "SunKid Carpet"]
    assert lifts[0] == {"Name": "Thundercloud Chair 1", "Status": "Closed", "StatusEnglish": "closed",
                        "Difficulty": None}
    trails = {trail["Name"]: trail for area in feed["MountainAreas"] for trail in area["Trails"]}
    assert len(trails) == 18 and {row["StatusEnglish"] for row in lifts + list(trails.values())} == {"closed"}
    assert trails["Snowbird"] == {"Name": "Snowbird", "Status": "Closed", "StatusEnglish": "closed",
                                  "Difficulty": "Green"}
    # "Cruisin' " is written with a space after it, which is not carried.
    assert trails["Cruisin'"]["Difficulty"] == "Green"
    assert (trails["Grizzly"]["Difficulty"], trails["Devil's Bowl"]["Difficulty"]) == ("Blue", "Black")
    assert trails["Screamin' Demon"]["Difficulty"] == "Double black"


def test_the_conditions_give_when_they_were_updated_and_no_depth_out_of_season():
    snow = skibigbear.parse(PAGE, NOW)["SnowReport"]
    # "2026-03-16T17:58:00.475Z".
    assert snow["LastUpdate"] == "2026-03-16T17:58:00Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": None}
    assert snow["BaseConditions"] is None and snow["SeasonTotalIn"] is None
    assert snow["Report"] == "Ski Big Bear is closed for the 2025-2026 season. We will see you in December!"


def test_in_season_the_base_depth_is_one_depth_or_a_least_and_a_most_and_the_surface_is_read():
    page = changed(SURFACE, SURFACE.replace("N/A", "Machine Groomed"))
    for said, read in (('30\\"', {"BaseIn": 30}), ("24 inches", {"BaseIn": 24}), ("18.5", {"BaseIn": 18.5}),
                       ('24\\" - 36\\"', {"BaseMinIn": 24, "BaseMaxIn": 36}),
                       ("20-40 inches", {"BaseMinIn": 20, "BaseMaxIn": 40}), ("", {"BaseIn": None})):
        snow = skibigbear.parse(changed(DEPTH, DEPTH.replace("N/A", said), page), NOW)["SnowReport"]
        assert snow["BaseArea"] == {"Name": "Mountain", **read}
        assert snow["BaseConditions"] == "Machine Groomed"


def test_an_open_lift_and_trail_are_read_in_the_page_s_words():
    page = changed('{"name":"Grizzly Chair","status":"Closed"}', '{"name":"Grizzly Chair","status":"Open"}')
    page = changed('{"name":"Little Bear Chair","status":"Closed"}', '{"name":"Little Bear Chair","status":"On Hold"}',
                   page)
    page = changed('{"name":"Grizzly","difficulty":"intermediate","status":"Closed"}',
                   '{"name":"Grizzly","difficulty":"intermediate","status":"Open"}', page)
    feed = skibigbear.parse(page, NOW)
    rows = [row for area in feed["MountainAreas"] for row in area["Lifts"] + area["Trails"]]
    assert [(row["Name"], row["Status"], row["StatusEnglish"]) for row in rows if row["StatusEnglish"] != "closed"] == [
        ("Little Bear Chair", "On hold", "on hold"), ("Grizzly Chair", "Open", "open"), ("Grizzly", "Open", "open")]


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="data was not found"):
        skibigbear.parse(changed("window.__remixContext", "window.__context"), NOW)
    with pytest.raises(ValueError, match="data could not be read"):
        skibigbear.parse(changed('"routes/_page.conditions-trail-map":', '"routes/_page.conditions":'), NOW)
    with pytest.raises(ValueError, match="no list of lifts or of trails"):
        skibigbear.parse(changed('"lifts":[', '"chairs":['), NOW)
    with pytest.raises(ValueError, match="difficulty the reader does not know"):
        skibigbear.parse(changed('"difficulty":"expert"', '"difficulty":"glades"'), NOW)
    with pytest.raises(ValueError, match="not a name and a status"):
        skibigbear.parse(changed('{"name":"SunKid Carpet","status":"Closed"}', '{"name":"SunKid Carpet"}'), NOW)
    with pytest.raises(ValueError, match="twice"):
        skibigbear.parse(changed('{"name":"Magic Carpet 2",', '{"name":"Magic Carpet 1",'), NOW)
    with pytest.raises(ValueError, match="no lifts or no trails"):
        skibigbear.parse(changed('"trails":[', '"trails":[],"runs":['), NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report(capsys):
    feed = skibigbear.parse(changed(DEPTH, DEPTH.replace("N/A", "plenty")), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 5
    assert "not inches" in capsys.readouterr().out
    assert "SnowReport" not in skibigbear.parse(changed('"date_updated":"2026-03-16T17:58:00.475Z"',
                                                        '"date_updated":null'), NOW)
    assert "SnowReport" not in skibigbear.parse(changed('"key":"Base Depth"', '"key":"Depth"'), NOW)
