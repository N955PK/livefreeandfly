import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import hoodmeadows

FIXTURES = Path(__file__).parent / "fixtures"
# The two reports as the site gave them on 2026-11-26, before the season: the "Lifts" sector holds no lifts.
PAGES = {name: (FIXTURES / f"hoodmeadows_{name}.json").read_text() for name in hoodmeadows.URLS}
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)
# Lifts in the fields the page's script reads (a name and "openingStatusCompl"): the site had posted none to save.
LIFTS = [{"id": "1", "name": "Mt. Hood Express", "openingStatusCompl": "OPEN"},
         {"id": "2", "name": "Cascade Express ", "openingStatusCompl": "DELAYED_WIND"},
         {"id": "3", "name": "Vista Express", "openingStatusCompl": "OUT_OF_PERIOD_SEASON_BEGINNING"},
         {"id": "4", "name": "Buttercup", "openingStatusCompl": "CLOSED"}]
COUNT = {"name": "Lifts", "open": 1, "pending": 1, "closed": 2}


def changed(name: str, change) -> dict:
    report = json.loads(PAGES[name])
    change(report)
    return {**PAGES, name: json.dumps(report)}


def posted(lifts: list = LIFTS, count: dict = COUNT) -> dict:
    def post(report):
        next(sector for sector in report["data"] if sector["name"] == "Lifts")["lifts"] = lifts
        report["counters"].append(count)
    return changed("lifts", post)


def test_the_reports_before_the_season_give_no_lifts():
    feed = hoodmeadows.parse(PAGES, NOW)
    assert feed["Name"] == "Mt. Hood Meadows" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    assert feed["MountainAreas"] == [{"Name": "Mt. Hood Meadows", "Lifts": [], "Trails": []}]


def test_posted_lifts_read_open_closed_or_in_the_report_s_words():
    feed = hoodmeadows.parse(posted(), NOW)
    assert feed["MountainAreas"] == [{"Name": "Mt. Hood Meadows", "Trails": [], "Lifts": [
        {"Name": "Mt. Hood Express", "Status": "Open", "StatusEnglish": "open", "Difficulty": None},
        {"Name": "Cascade Express", "Status": "Delayed wind", "StatusEnglish": "delayed wind", "Difficulty": None},
        {"Name": "Vista Express", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None},
        {"Name": "Buttercup", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}]}]


def test_the_snow_report_gives_both_zones_and_when_it_was_last_changed():
    snow = hoodmeadows.parse(PAGES, NOW)["SnowReport"]
    # Last changed "2026-05-05T10:23:00.000-07:00", at the end of last season: the runner leaves so old a report out.
    assert snow["LastUpdate"] == "2026-05-05T17:23:00Z" and snow["Resortwide"] is False
    assert snow["BaseArea"] == {"Name": "Base Area", "BaseIn": 0, "Last24HoursIn": 0, "Last48HoursIn": 0,
                                "Last72HoursIn": 0, "Last7DaysIn": 0, "OvernightIn": 1}
    assert snow["MidMountainArea"] == {**snow["BaseArea"], "Name": "Mid-Mountain"}
    assert snow["SeasonTotalIn"] == 0 and snow["BaseConditions"] == "Closed for the season"
    assert snow["Report"].startswith("Monday, November 16: We got a dusting of snow") and snow["Alert"] is None

    def midwinter(report):
        base, mid = report["data"]["snow"]["snowZones"]
        base["snowTotalDepth"].update(countryValue=84)
        base["freshSnowFallDepth24H"].update(countryValue=6.5)
        base["snowFallDepthCompleteSeason"].update(countryValue=212)
        mid["snowTotalDepth"].update(countryValue=110)
        mid["lastModified"] = "2027-01-15T05:40:00.000-08:00"
    snow = hoodmeadows.parse(changed("snow", midwinter), NOW)["SnowReport"]
    assert (snow["BaseArea"]["BaseIn"], snow["BaseArea"]["Last24HoursIn"], snow["SeasonTotalIn"]) == (84, 6.5, 212)
    assert snow["MidMountainArea"]["BaseIn"] == 110 and snow["LastUpdate"] == "2027-01-15T13:40:00Z"


def test_reports_that_are_missing_or_changed_are_refused():
    with pytest.raises(ValueError, match="does not read as JSON"):
        hoodmeadows.parse({**PAGES, "lifts": "<html>"}, NOW)
    with pytest.raises(ValueError, match="not an object"):
        hoodmeadows.parse({**PAGES, "lifts": "[]"}, NOW)
    with pytest.raises(ValueError, match="0 sectors named Lifts"):
        hoodmeadows.parse(PAGES | {"lifts": PAGES["lifts"].replace('"name":"Lifts"', '"name":"Chairs"')}, NOW)
    with pytest.raises(ValueError, match="not in the shape expected"):
        hoodmeadows.parse(changed("lifts", lambda report: report.pop("counters")), NOW)
    with pytest.raises(ValueError, match="not in the shape expected"):
        hoodmeadows.parse(posted([{"name": "Mt. Hood Express", "status": "OPEN"}]), NOW)
    with pytest.raises(ValueError, match="status the reader does not know: 'SPINNING'"):
        hoodmeadows.parse(posted([{**LIFTS[0], "openingStatusCompl": "SPINNING"}, *LIFTS[1:]]), NOW)
    with pytest.raises(ValueError, match="a lift with no name"):
        hoodmeadows.parse(posted([{**LIFTS[0], "name": " "}, *LIFTS[1:]]), NOW)
    with pytest.raises(ValueError, match="counts 4 lifts but 3 were read"):
        hoodmeadows.parse(posted(LIFTS[:3]), NOW)
    with pytest.raises(ValueError, match="counts 4 lifts but 0 were read"):
        hoodmeadows.parse(posted([]), NOW)
    with pytest.raises(ValueError, match="lists a lift twice"):
        hoodmeadows.parse(posted([LIFTS[0], LIFTS[0], *LIFTS[2:]]), NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    def metric(report):
        report["data"]["snow"]["snowZones"][0]["snowTotalDepth"]["countryUnit"] = "CENTIMETER"
    feed = hoodmeadows.parse({**posted(), "snow": changed("snow", metric)["snow"]}, NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"][0]["Lifts"]) == 4
    assert "SnowReport" not in hoodmeadows.parse({**PAGES, "snow": "<html>"}, NOW)
    assert "SnowReport" not in hoodmeadows.parse(changed("snow", lambda report: report["data"].pop("snow")), NOW)
    assert "SnowReport" not in hoodmeadows.parse(
        changed("snow", lambda report: report["data"]["snow"]["snowZones"].pop(0)), NOW)
    assert "SnowReport" not in hoodmeadows.parse(
        changed("snow", lambda report: report["data"]["snow"]["snowZones"][1].update(lastModified="May")), NOW)
