from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import loveland

FIXTURES = Path(__file__).parent / "fixtures"
# Both pages with their scripts, styles, drawings and comments taken out; the reader gives the same on the whole pages.
PAGES = {name: (FIXTURES / f"loveland_{name}.html").read_text() for name in loveland.URLS}
NOW = datetime(2026, 11, 24, 18, 0, tzinfo=timezone.utc)


def lifts_page(old: str, new: str) -> dict:
    assert old in PAGES["lifts"]
    return {**PAGES, "lifts": PAGES["lifts"].replace(old, new)}


def snow_page(old: str, new: str) -> dict:
    assert old in PAGES["snow"]
    return {**PAGES, "snow": PAGES["snow"].replace(old, new)}


def test_the_early_season_mountain_reads_each_lift_with_the_trails_under_it():
    # Loveland's pages on 2026-11-24, early season: ten lifts with three open, 94 trails.
    feed = loveland.parse(PAGES, NOW)
    assert feed["Name"] == "Loveland" and feed["LastUpdate"] == "2026-11-24T18:00:00Z"
    assert [(area["Name"], area["Lifts"][0]["Status"], len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Rainbow Magic Carpet", "Open", 2), ("Chet's Dream", "Open", 19), ("Lift 2", "Closed", 2),
        ("Ptarmigan Lift", "Closed", 12), ("Lift 3", "Closed", 5), ("Lift 4", "Closed", 17), ("Lift 6", "Closed", 10),
        ("Lift 7", "Open", 0), ("Lift 8", "Closed", 11), ("Lift 9", "Closed", 16)]
    assert all(len(area["Lifts"]) == 1 for area in feed["MountainAreas"])
    areas = {area["Name"]: area for area in feed["MountainAreas"]}
    assert areas["Chet's Dream"]["Lifts"] == [{"Name": "Chet's Dream", "Status": "Open", "StatusEnglish": "open",
                                               "Difficulty": None}]
    # "Lift 7 -OPEN" has no space after its dash, and "PTARMIGAN LIFT" is written as the table of elevations has it.
    assert areas["Lift 7"]["Lifts"][0]["StatusEnglish"] == "open"
    assert areas["Ptarmigan Lift"]["Lifts"][0]["StatusEnglish"] == "closed"
    assert areas["Chet's Dream"]["Trails"][0] == {"Name": "Catwalk", "Status": "Open", "StatusEnglish": "open",
                                                  "Difficulty": "Green", "Grooming": "Yes"}
    assert areas["Rainbow Magic Carpet"]["Trails"][0] == {"Name": "All Smiles", "Status": "Closed",
                                                          "StatusEnglish": "closed", "Difficulty": "Green",
                                                          "Grooming": "No"}
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    # Take Off and All Smiles are listed under the carpet and again under Lift 7: each is read once.
    assert len(trails) == 94 == len({trail["Name"] for trail in trails})
    assert sorted(trail["Name"] for trail in trails if trail["StatusEnglish"] == "open") == [
        "Catwalk", "Home Run", "Mambo", "Spillway", "Take Off"]
    assert {trail["Difficulty"] for trail in trails} == {"Green", "Blue", "Black", "Double black", ""}
    assert [trail["Name"] for trail in trails if trail["Difficulty"] == ""] == ["Royal Flush", "Straight Flush"]


def test_the_snow_report_gives_the_mid_mountain_depth_and_when_it_was_written():
    snow = loveland.parse(PAGES, NOW)["SnowReport"]
    # "6:00 AM REPORT – November 24, 2026", seven hours behind UTC in November.
    assert snow["LastUpdate"] == "2026-11-24T13:00:00Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Mid-mountain", "Last24HoursIn": 1, "Last48HoursIn": 1, "Last72HoursIn": 1,
                                "BaseIn": 18}
    assert snow["SeasonTotalIn"] == 10.5 and snow["BaseConditions"] is None


def test_an_all_closed_mountain_reads_as_closed():
    pages = {**PAGES, "lifts": PAGES["lifts"].replace("icon_open.png", "icon_closed.png").replace("OPEN</h2>",
                                                                                                 "CLOSED</h2>")}
    feed = loveland.parse(pages, NOW)
    rows = [row for area in feed["MountainAreas"] for row in area["Lifts"] + area["Trails"]]
    assert len(rows) == 104 and {row["StatusEnglish"] for row in rows} == {"closed"}


def test_a_lift_s_other_status_is_carried_in_the_page_s_words():
    feed = loveland.parse(lifts_page("Lift 4 - CLOSED</h2>", "Lift 4 - ON HOLD</h2>"), NOW)
    lift = feed["MountainAreas"][5]["Lifts"][0]
    assert (lift["Name"], lift["Status"], lift["StatusEnglish"]) == ("Lift 4", "On hold", "on hold")


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="not a name, a dash and a status"):
        loveland.parse(lifts_page("Lift 4 - CLOSED</h2>", "Lift 4</h2>"), NOW)
    with pytest.raises(ValueError, match="status pictures"):
        loveland.parse(lifts_page("icon_closed.png", "icon_shut.png"), NOW)
    with pytest.raises(ValueError, match="difficulty pictures"):
        loveland.parse(lifts_page("icon_expert.png", "icon_hardest.png"), NOW)
    with pytest.raises(ValueError, match="lift elevations was not found"):
        loveland.parse(lifts_page(">BOTTOM<", ">BASE<"), NOW)
    with pytest.raises(ValueError, match="were not read: \\['Lift 9'\\]"):
        loveland.parse(lifts_page("id=\"tablepress-13-name\"", "id=\"tablepress-13-title\""), NOW)
    with pytest.raises(ValueError, match="counts 11 lifts but 10"):
        loveland.parse(snow_page("of 10 LIFTS", "of 11 LIFTS"), NOW)
    with pytest.raises(ValueError, match="no lifts or no trails"):
        loveland.parse({**PAGES, "lifts": PAGES["lifts"].replace("tablepress-table-name ", "table-name ")}, NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = loveland.parse(snow_page('<span class="mid-mtn-total" style="color: #003366;">18" </span>',
                                    '<span class="mid-mtn-total" style="color: #003366;">deep</span>'), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 10
    assert "SnowReport" not in loveland.parse(snow_page("6:00 AM REPORT", "MORNING REPORT"), NOW)
    assert "SnowReport" not in loveland.parse(snow_page("MID-MTN", "SUMMIT"), NOW)
