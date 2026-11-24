from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import orford

FIXTURES = Path(__file__).parent / "fixtures"
# The pages with their scripts, styles, drawings and comments taken out; the reader gives the same on the whole pages.
PAGE = (FIXTURES / "orford.html").read_text()
MIDSEASON = (FIXTURES / "orford_midseason.html").read_text()
NOW = datetime(2026, 11, 24, 18, 0, tzinfo=timezone.utc)


def changed(old: str, new: str, page: str = PAGE) -> str:
    assert old in page
    return page.replace(old, new)


def rows(feed: dict, kind: str) -> list:
    return [row for area in feed["MountainAreas"] for row in area[kind]]


def test_the_closed_mountain_reads_its_lifts_and_trails_by_part_of_the_mountain():
    # Mont Orford's page on 2026-11-24, before the season: seven lifts and 65 trails, all closed.
    feed = orford.parse(PAGE, NOW)
    assert feed["Name"] == "Mont Orford" and feed["LastUpdate"] == "2026-11-24T18:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Mont-Orford", 2, 30), ("Mont Alfred-DesRochers", 1, 7), ("Mont Giroux Nord", 3, 18),
        ("Mont Giroux Est", 1, 10)]
    assert [lift["Name"] for lift in rows(feed, "Lifts")] == [
        "Rapido", "Gondole hybride", "Alfred-Desrochers", "Quad Giroux Nord", "Tapis Giroux", "Tapis Orford",
        "Quad Giroux Est"]
    assert rows(feed, "Lifts")[0] == {"Name": "Rapido", "Status": "Closed", "StatusEnglish": "closed",
                                      "Difficulty": None}
    assert {row["StatusEnglish"] for row in rows(feed, "Lifts") + rows(feed, "Trails")} == {"closed"}
    assert rows(feed, "Trails")[0] == {"Name": "Trois Ruisseaux", "Status": "Closed", "StatusEnglish": "closed",
                                       "Difficulty": "Black", "Grooming": "No"}
    assert {trail["Difficulty"] for trail in rows(feed, "Trails")} == {"Green", "Blue", "Black", "Double black"}


def test_the_midseason_mountain_reads_what_is_open_and_groomed():
    # The page as the Internet Archive kept it on 2026-03-02: five of seven lifts turning.
    feed = orford.parse(MIDSEASON, NOW)
    assert [(lift["Name"], lift["StatusEnglish"]) for lift in rows(feed, "Lifts")] == [
        ("Rapido", "closed"), ("Gondole hybride", "open"), ("Alfred-Desrochers", "open"), ("Quad Giroux Nord", "open"),
        ("Tapis Giroux", "open"), ("Tapis Orford", "open"), ("Quad Giroux Est", "closed")]
    trails = rows(feed, "Trails")
    assert len(trails) == 65 and sum(trail["StatusEnglish"] == "open" for trail in trails) == 44
    assert sum(trail["Grooming"] == "Yes" for trail in trails) == 27
    assert trails[0] == {"Name": "Trois Ruisseaux", "Status": "Open", "StatusEnglish": "open", "Difficulty": "Black",
                         "Grooming": "Yes"}


def test_the_snowfall_is_turned_from_centimetres_into_inches_and_there_is_no_depth():
    snow = orford.parse(MIDSEASON, NOW)["SnowReport"]
    # "Update the 2026-03-02 at 06:24:46", five hours behind UTC in March; 0, 2, 12 and 426 cm.
    assert snow["LastUpdate"] == "2026-03-02T11:24:46Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Mountain", "Last24HoursIn": 0.0, "Last48HoursIn": 0.8, "Last7DaysIn": 4.7}
    assert snow["SeasonTotalIn"] == 167.7 and snow["BaseConditions"] == "Groomed Snow"
    assert orford.parse(PAGE, NOW)["SnowReport"]["LastUpdate"] == "2026-11-18T14:32:24Z"


def test_the_page_s_other_statuses_are_carried_in_its_words():
    feed = orford.parse(changed('data-tippy="Open Groomed"', 'data-tippy="Progressive opening"', MIDSEASON), NOW)
    assert rows(feed, "Trails")[0]["Status"] == "Progressive opening"
    assert rows(feed, "Trails")[0]["StatusEnglish"] == "progressive opening"
    assert rows(feed, "Trails")[0]["Grooming"] == "No"


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="not one the reader knows"):
        orford.parse(changed('data-tippy="Closed"', 'data-tippy="Shut"'), NOW)
    with pytest.raises(ValueError, match="has the level"):
        orford.parse(changed('data-tippy="Extreme"', 'data-tippy="Hardest"'), NOW)
    with pytest.raises(ValueError, match="counts 8 lifts but 7"):
        orford.parse(changed('<span class="total">/5</span>', '<span class="total">/6</span>'), NOW)
    with pytest.raises(ValueError, match="counts 66 trails but 65"):
        orford.parse(changed('<span class="total">/43</span>', '<span class="total">/44</span>'), NOW)
    with pytest.raises(ValueError, match="the page has no"):
        orford.parse(changed("conditions-tracks -chairlifts", "conditions-tracks -lifts"), NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = orford.parse(changed("Update the 2026-11-18 at", "Updated"), NOW)
    assert "SnowReport" not in feed and len(rows(feed, "Lifts")) == 7
    assert "SnowReport" not in orford.parse(changed('data-key="today"', 'data-key="day"'), NOW)
