import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import skisantafe

FIXTURES = Path(__file__).parent / "fixtures"
# The three reports as the site gave them, but for the alert's author, which is taken out.
PAGES = {name: (FIXTURES / f"skisantafe_{name}.json").read_text() for name in skisantafe.URLS}
NOW = datetime(2026, 11, 26, 14, 0, tzinfo=timezone.utc)


def changed(name: str, change) -> dict:
    report = json.loads(PAGES[name])
    change(report)
    return {**PAGES, name: json.dumps(report)}


def test_opening_day_reads_its_four_open_lifts_by_part_of_the_mountain():
    # Ski Santa Fe's reports on 2026-11-26, its opening day: seven lifts with four open, 89 trails with nine open.
    feed = skisantafe.parse(PAGES, NOW)
    assert feed["Name"] == "Ski Santa Fe" and feed["LastUpdate"] == "2026-11-26T14:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Lower Mountain", 5, 43), ("Upper Mountain", 2, 46)]
    lifts = {lift["Name"]: lift for area in feed["MountainAreas"] for lift in area["Lifts"]}
    assert sorted(name for name, lift in lifts.items() if lift["StatusEnglish"] == "open") == [
        "Easy Street", "Pine Flats", "Santa Fe Express", "Sierra"]
    assert lifts["Santa Fe Express"] == {"Name": "Santa Fe Express", "Status": "Open", "StatusEnglish": "open",
                                         "Difficulty": None}
    assert lifts["Tesuque Peak"]["Status"] == "Closed" and lifts["Millennium"]["Status"] == "Closed"
    trails = {trail["Name"]: trail for area in feed["MountainAreas"] for trail in area["Trails"]}
    assert len(trails) == 89
    assert sorted(name for name, trail in trails.items() if trail["StatusEnglish"] == "open") == [
        "Davey Lane", "Easy Street", "JC", "Lower Gayway", "Lower Midland", "Midland", "Pine Flats", "Riblet Road",
        "Upper Midland"]
    assert trails["Midland"]["Grooming"] == "Yes" and trails["JC"]["Grooming"] == "No"
    assert sum(trail["Grooming"] == "Yes" for trail in trails.values()) == 7
    assert trails["Buena Vista Terrain Park"] == {"Name": "Buena Vista Terrain Park", "Status": "Closed",
                                                  "StatusEnglish": "closed", "Difficulty": "", "Grooming": "No"}
    levels = [trail["Difficulty"] for trail in trails.values()]
    assert {level: levels.count(level) for level in set(levels)} == {"Green": 15, "Blue": 26, "Black": 40,
                                                                     "Double black": 5, "": 3}


def test_the_snow_report_gives_the_base_depth_snowfall_and_when_it_was_written():
    snow = skisantafe.parse(PAGES, NOW)["SnowReport"]
    assert snow["LastUpdate"] == "2026-11-26T12:18:26Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Base", "BaseIn": 20, "Last12HoursIn": 0, "Last24HoursIn": 0,
                                "Last48HoursIn": 0, "Last72HoursIn": 3, "Last7DaysIn": 6}
    assert snow["SeasonTotalIn"] == 20 and snow["StormTotalIn"] == 0 and snow["BaseConditions"] is None
    # The summit's depth reads 0, which is the resort not measuring it.
    assert "SummitArea" not in snow

    def measured(report):
        report["weather"]["snowReport"]["summitDepth"] = 31
    assert skisantafe.parse(changed("conditions", measured), NOW)["SnowReport"]["SummitArea"] == {"Name": "Summit",
                                                                                                 "BaseIn": 31}


def test_a_lift_on_hold_takes_the_report_s_words():
    def hold(report):
        report["docs"][0]["status"] = "Wind Hold"
    lift = skisantafe.parse(changed("lifts", hold), NOW)["MountainAreas"][0]["Lifts"][0]
    assert (lift["Name"], lift["Status"], lift["StatusEnglish"]) == ("Santa Fe Express", "Wind hold", "wind hold")


def test_an_all_closed_mountain_reads_as_closed():
    def shut(report):
        for row in report["docs"]:
            row["status"] = "Closed"
    feed = skisantafe.parse({**changed("lifts", shut), "trails": changed("trails", shut)["trails"]}, NOW)
    rows = [row for area in feed["MountainAreas"] for row in area["Lifts"] + area["Trails"]]
    assert len(rows) == 96 and {row["StatusEnglish"] for row in rows} == {"closed"}


def test_reports_that_have_changed_are_refused():
    def cut(report):
        report["docs"].pop()

    def paged(report):
        report["hasNextPage"] = True

    def harder(report):
        report["docs"][0]["difficulty"] = "Triple Black"

    def nowhere(report):
        report["docs"][0]["area"] = None

    def unsaid(report):
        report["docs"][0]["status"] = ""

    def miscounted(report):
        report["totalLifts"] = 8

    with pytest.raises(ValueError, match="does not read as JSON"):
        skisantafe.parse({**PAGES, "lifts": "<html>Loading lift status...</html>"}, NOW)
    with pytest.raises(ValueError, match="not a list of rows"):
        skisantafe.parse({**PAGES, "lifts": "[]"}, NOW)
    with pytest.raises(ValueError, match="says it has 89 rows but gives 88"):
        skisantafe.parse(changed("trails", cut), NOW)
    with pytest.raises(ValueError, match="trail report says it has"):
        skisantafe.parse(changed("trails", paged), NOW)
    with pytest.raises(ValueError, match="difficulty the reader does not know: Triple Black"):
        skisantafe.parse(changed("trails", harder), NOW)
    with pytest.raises(ValueError, match="Santa Fe Express does not name its part of the mountain"):
        skisantafe.parse(changed("lifts", nowhere), NOW)
    with pytest.raises(ValueError, match="Santa Fe Express has no status"):
        skisantafe.parse(changed("lifts", unsaid), NOW)
    with pytest.raises(ValueError, match="counts 8 lifts and 89 trails but 7 and 89"):
        skisantafe.parse(changed("conditions", miscounted), NOW)
    with pytest.raises(ValueError, match="no lifts or no trails"):
        skisantafe.parse({**PAGES, "lifts": json.dumps({"docs": [], "totalDocs": 0, "hasNextPage": False}),
                          "conditions": json.dumps({"totalLifts": 0, "totalTrails": 89})}, NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    def deep(report):
        report["weather"]["snowReport"]["baseDepth"] = "deep"

    def undated(report):
        report["snowReportLastUpdated"] = None

    def gone(report):
        del report["weather"]

    feed = skisantafe.parse(changed("conditions", deep), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 2
    assert "SnowReport" not in skisantafe.parse(changed("conditions", undated), NOW)
    assert "SnowReport" not in skisantafe.parse(changed("conditions", gone), NOW)
