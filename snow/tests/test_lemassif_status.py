import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import lemassif

FIXTURES = Path(__file__).parent / "fixtures"
# Both pages with their scripts, styles, drawings and comments taken out; the reader gives the same on the whole pages.
PAGES = {name: (FIXTURES / f"lemassif_{name}.html").read_text() for name in lemassif.URLS}
NOW = datetime(2026, 11, 24, 23, 45, tzinfo=timezone.utc)


def lifts_page(old: str, new: str, count: int = -1) -> dict:
    assert old in PAGES["lifts"]
    return {**PAGES, "lifts": PAGES["lifts"].replace(old, new, count)}


def snow_page(old: str, new: str) -> dict:
    assert old in PAGES["snow"]
    return {**PAGES, "snow": PAGES["snow"].replace(old, new)}


def rows(feed: dict, kind: str) -> list:
    return [row for area in feed["MountainAreas"] for row in area[kind]]


def test_the_closed_mountain_reads_its_lifts_and_its_trails_by_part_of_the_mountain():
    # Le Massif's pages on 2026-11-24, before the season: eight lifts and 62 trails, all closed.
    feed = lemassif.parse(PAGES, NOW)
    assert feed["Name"] == "Le Massif de Charlevoix" and feed["LastUpdate"] == "2026-11-24T23:45:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Le Massif de Charlevoix", 8, 0), ("Beginner area", 0, 3), ("Camp-Boule", 0, 13), ("Grande-Pointe", 0, 29),
        ("Maillard", 0, 13), ("Snowpark", 0, 1), ("Off-piste area", 0, 2), ("Alpine touring", 0, 1)]
    assert [lift["Name"] for lift in rows(feed, "Lifts")] == [
        "Camp-Boule Express", "Grande-Pointe Express", "Magic carpet base", "Magic carpet summit", "Maillard Express",
        "Massif Express (Gondolas)", "Teleski learning area base", "Teleski learning area summit"]
    assert rows(feed, "Lifts")[0] == {"Name": "Camp-Boule Express", "Status": "Closed", "StatusEnglish": "closed",
                                      "Difficulty": None}
    # The ascent trails' row is left in French on the English page: its "Fermé" is Closed like the rest.
    assert {row["Status"] for row in rows(feed, "Lifts") + rows(feed, "Trails")} == {"Closed"}
    assert rows(feed, "Trails")[0] == {"Name": "Brise-Glace", "Status": "Closed", "StatusEnglish": "closed",
                                       "Difficulty": "Green", "Grooming": "No"}
    assert rows(feed, "Trails")[-1]["Name"] == "Off-piste - ascent trails"
    assert {trail["Difficulty"] for trail in rows(feed, "Trails")} == {"Green", "Blue", "Black", "Double black"}


def test_an_open_lift_and_a_groomed_trail_are_read():
    pages = lifts_page('<div class="cell d-flex jc-center status closed">\n <div class="icon" title="Closed">',
                       '<div class="cell d-flex jc-center status open">\n <div class="icon" title="Open">', 9)
    feed = lemassif.parse(pages, NOW)
    assert [lift["StatusEnglish"] for lift in rows(feed, "Lifts")] == ["open"] * 8
    assert [trail["StatusEnglish"] for trail in rows(feed, "Trails")][:2] == ["open", "closed"]
    pages = lifts_page('<span class="d-block condition-icon tid-147" title="Maintenance">',
                       '<span class="d-block condition-icon tid-22" title="Groomed">')
    assert [trail["Name"] for trail in rows(lemassif.parse(pages, NOW), "Trails") if trail["Grooming"] == "Yes"] == [
        "Off-piste - sector 1,2,3,4"]


def test_the_snowfall_is_turned_from_centimetres_into_inches_and_there_is_no_depth():
    snow = lemassif.parse(PAGES, NOW)["SnowReport"]
    # "Updated: Nov 24 - 6:18pm" is the later of the snowfall's two lines, five hours behind UTC; 2 cm in 7 days.
    assert snow["LastUpdate"] == "2026-11-24T23:18:00Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Mountain", "Last24HoursIn": 0.0, "Last48HoursIn": 0.0, "Last7DaysIn": 0.8}
    assert snow["SeasonTotalIn"] == 0.8 and snow["BaseConditions"] is None
    # Read in January, a December line belongs to the year before.
    january = datetime(2027, 1, 2, 12, 0, tzinfo=timezone.utc)
    pages = {**PAGES, "snow": re.sub(r"Updated:\s*Nov 24", "Updated: Dec 30", PAGES["snow"])}
    assert pages != PAGES and lemassif.parse(pages, january)["SnowReport"]["LastUpdate"] == "2026-12-30T23:18:00Z"


def test_pages_that_have_changed_are_refused():
    with pytest.raises(ValueError, match="status titles"):
        lemassif.parse(lifts_page('title="Closed"', 'title="Standby"'), NOW)
    with pytest.raises(ValueError, match="level symbols"):
        lemassif.parse(lifts_page("level level-19", "level level-20"), NOW)
    with pytest.raises(ValueError, match="counts 9 lifts but 8"):
        lemassif.parse(lifts_page('<span class="unit">/8</span>', '<span class="unit">/9</span>'), NOW)
    with pytest.raises(ValueError, match="counts 63 trails but only 62"):
        lemassif.parse(lifts_page('<span class="unit">/53</span>', '<span class="unit">/63</span>'), NOW)
    with pytest.raises(ValueError, match="lifts part of the page"):
        lemassif.parse(lifts_page("<h2>Lift Status</h2>", "<h2>Lifts</h2>"), NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = lemassif.parse(snow_page("Updated:", "As of"), NOW)
    assert "SnowReport" not in feed and len(rows(feed, "Lifts")) == 8
    assert "SnowReport" not in lemassif.parse(snow_page("24 Hours", "One day"), NOW)
