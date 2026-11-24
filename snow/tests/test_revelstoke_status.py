from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import revelstoke

FIXTURES = Path(__file__).parent / "fixtures"
# Of each page, only the block its figures are in, with its drawings taken out; the reader gives the same on the
# whole pages.
PAGES = {name: (FIXTURES / f"revelstoke_{name}.html").read_text() for name in revelstoke.URLS}
NOW = datetime(2026, 11, 25, 1, 0, tzinfo=timezone.utc)
CLOSED_RUN = "<span class=\"run-status run-status--closed\">\n  \n  <span class=\"status-text\">Closed</span>"
CLOSED_LIFT = "<span class=\"lift-status lift-status--closed\">\n  \n  <span class=\"status-text\">Closed</span>"


def page(name: str, old: str, new: str, count: int = -1) -> dict:
    assert old in PAGES[name]
    return {**PAGES, name: PAGES[name].replace(old, new, count)}


def test_the_closed_mountain_reads_each_lift_with_the_runs_under_it():
    # Revelstoke's pages on 2026-11-24, eleven days before it opens: 4 lifts, all closed, and 42 listings of the
    # 35 runs it grooms, two of them still marked open from the summer's page.
    feed = revelstoke.parse(PAGES, NOW)
    assert feed["Name"] == "Revelstoke" and feed["LastUpdate"] == "2026-11-25T01:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Stoke Chair", 1, 10), ("Stellar Chair", 1, 5), ("Ripper Chair", 1, 5),
        ("Stoke Base to Revelation Lodge", 1, 14), ("Revelation Lodge to Village Base", 0, 8)]
    areas = {area["Name"]: area for area in feed["MountainAreas"]}
    assert areas["Stoke Chair"]["Lifts"] == [{"Name": "Stoke Chair", "Status": "Closed", "StatusEnglish": "closed",
                                              "Difficulty": None}]
    assert areas["Stoke Chair"]["Trails"][0] == {"Name": "The Last Spike", "Status": "Closed",
                                                 "StatusEnglish": "closed", "Difficulty": "Green", "Grooming": "No"}
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    assert len(trails) == 42 and len({trail["Name"] for trail in trails}) == 35
    assert {trail["Difficulty"] for trail in trails} == {"Green", "Blue", "Black"}
    assert [(trail["Name"], trail["Status"]) for trail in trails if trail["StatusEnglish"] != "closed"] == [
        ("Burn Down", "Open"), ("Chopper", "Open")]
    # A run under two lifts is listed under each, here at two difficulties.
    assert [trail["Difficulty"] for trail in trails if trail["Name"] == "Snow Rodeo"] == ["Black", "Blue", "Blue"]
    assert "Bread & Butter" in {trail["Name"] for trail in trails}


def test_the_snow_report_is_in_inches_from_the_page_s_centimetres():
    snow = revelstoke.parse(PAGES, NOW)["SnowReport"]
    # 39 cm of base; 1 cm in 24 hours, 2 cm in 48 hours, 24 cm in 7 days and 182 cm this season. The page's "new
    # snow" and "last hour" are not read, and the page does not date the report.
    assert snow["BaseArea"] == {"Name": "Mountain", "Last24HoursIn": 0.4, "Last48HoursIn": 0.8, "Last7DaysIn": 9.4,
                                "BaseIn": 15.4}
    assert snow["SeasonTotalIn"] == 71.7 and snow["LastUpdate"] is None and snow["Resortwide"] is True
    assert snow["BaseConditions"] is None


def test_open_groomed_and_standby_rows_are_read_in_the_page_s_own_marks():
    pages = page("lifts", CLOSED_LIFT, CLOSED_LIFT.replace("--closed", "--open").replace("Closed", "Open"), 1)
    pages["lifts"] = (pages["lifts"]
                      .replace(CLOSED_LIFT, CLOSED_LIFT.replace("--closed", "--standby").replace("Closed", "Standby"), 1)
                      .replace(CLOSED_RUN, CLOSED_RUN.replace("--closed", "--groomed").replace("Closed", "Groomed"), 1)
                      .replace(CLOSED_RUN, CLOSED_RUN.replace("--closed", "--ungroomed").replace("Closed", "Ungroomed"), 1))
    feed = revelstoke.parse(pages, NOW)
    lifts = [lift for area in feed["MountainAreas"] for lift in area["Lifts"]]
    assert [(lift["Name"], lift["Status"], lift["StatusEnglish"]) for lift in lifts[:3]] == [
        ("Stoke Chair", "Open", "open"), ("Stellar Chair", "Standby", "standby"), ("Ripper Chair", "Closed", "closed")]
    trails = feed["MountainAreas"][0]["Trails"]
    assert [(trail["Name"], trail["Status"], trail["Grooming"]) for trail in trails[:3]] == [
        ("The Last Spike", "Open", "Yes"), ("Greenhorn", "Open", "No"), ("Ripper Connector", "Closed", "No")]


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="The Last Spike has a status the reader does not know: patrol"):
        revelstoke.parse(page("lifts", "run-status run-status--closed", "run-status run-status--patrol", 1), NOW)
    with pytest.raises(ValueError, match="Stoke Chair has a status the reader does not know: hold"):
        revelstoke.parse(page("lifts", "lift-status lift-status--closed", "lift-status lift-status--hold", 1), NOW)
    with pytest.raises(ValueError, match="Snow Rodeo has a difficulty the reader does not know: double-black"):
        revelstoke.parse(page("lifts", "run-difficulty black", "run-difficulty double-black", 1), NOW)
    with pytest.raises(ValueError, match="Stoke Chair lists 10 runs but 9 were read"):
        revelstoke.parse(page("lifts", "<td class=\"run-info\">", "<td class=\"run-status\">", 1), NOW)
    with pytest.raises(ValueError, match="has 5 panels but 4 were read"):
        revelstoke.parse(page("lifts", "<div class=\"lifts-runs__header\">", "<div class=\"lifts-runs__head\">", 1),
                         NOW)
    with pytest.raises(ValueError, match="Stoke Chair does not read as a lift and its status"):
        revelstoke.parse(page("lifts", "<span class=\"lift-status lift-status--closed\">",
                              "<span class=\"lift-status\">", 1), NOW)
    with pytest.raises(ValueError, match="no lifts or no runs"):
        revelstoke.parse({**PAGES, "lifts": "<main></main>"}, NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    for old, new in (("<span class=\"value\">39</span>", "<span class=\"value\">--</span>"),
                     ("Base Depth", "Snow Depth"), ("snow-report__section", "snow-report"),
                     ("<span class=\"unit\">cm</span>", "<span class=\"unit\">in</span>"),
                     ("<h2 class=\"snow-report__title\">24 hours</h2>", "<h2 class=\"snow-report__title\">Last Hour</h2>")):
        feed = revelstoke.parse(page("snow", old, new), NOW)
        assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 5
