from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import wisp

# The page with its scripts, styles, drawings and comments taken out; the reader gives the same on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "wisp.html").read_text()
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)
LIFT_CLOSED = "<td data-title=\"Status\" class=\"closed\">closed</td>"
RUN_CLOSED = "<td data-title=\"Status\" class=\"closed\"><img"
BLANK = "<h6>{label}</h6>\n <h3>”</h3>"


def page(old: str, new: str, count: int = -1) -> str:
    assert old in PAGE
    return PAGE.replace(old, new, count)


def figure(text: str, label: str, said: str) -> str:
    assert BLANK.format(label=label) in text
    return text.replace(BLANK.format(label=label), BLANK.format(label=label).replace("”", said))


def test_the_closed_mountain_reads_its_lifts_and_the_runs_of_each_part_of_the_mountain():
    # Wisp's page on 2026-11-26, before it opened: ten lifts and 34 runs, all closed, and blank snow figures.
    feed = wisp.parse(PAGE, NOW)
    assert feed["Name"] == "Wisp" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    assert "SnowReport" not in feed
    # The Mountain Park's coaster and tubing are left out.
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Wisp", 10, 0), ("Front Side Trails", 0, 19), ("North Camp Trails", 0, 9), ("East Ridge Trails", 0, 6)]
    lifts = feed["MountainAreas"][0]["Lifts"]
    assert [lift["Name"] for lift in lifts] == [
        "Chair 1", "Chair 2", "Chair 3", "Chair 4", "Chair 5", "Chair 6", "Chair 7", "Central Park Handle Tow",
        "Sunset Carpet 1", "Sunset Carpet 2"]
    assert lifts[0] == {"Name": "Chair 1", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    assert {trail["StatusEnglish"] for trail in trails + lifts} == {"closed"}
    assert trails[0] == {"Name": "Happy Camper", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": "Green"}
    levels = {trail["Name"]: trail["Difficulty"] for trail in trails}
    assert (levels["Wisp Trail"], levels["The Face"], levels["Central Park Terrain"]) == ("Blue", "Black", "")
    assert not {"Mountain Coaster", "Snow Tubing"} & set(levels)


def test_the_snow_report_is_read_once_the_page_gives_its_figures():
    filled = figure(figure(figure(PAGE, "Current Base", "24”"), "Last 24 hrs.", "3”"), "Season Total", "41.5”")
    snow = wisp.parse(filled, NOW)["SnowReport"]
    # The page does not say when its figures were written.
    assert snow["LastUpdate"] is None and snow["Resortwide"] is True and snow["SeasonTotalIn"] == 41.5
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": 24, "OvernightIn": None, "Last24HoursIn": 3,
                                "Last48HoursIn": None}
    ranged = wisp.parse(figure(PAGE, "Current Base", "18-36”"), NOW)["SnowReport"]["BaseArea"]
    assert (ranged["BaseMinIn"], ranged["BaseMaxIn"]) == (18, 36) and "BaseIn" not in ranged


def test_an_open_lift_and_run_are_read_in_the_page_s_words():
    opened = page(LIFT_CLOSED, "<td data-title=\"Status\" class=\"open\">open</td>", 2)
    lifts = wisp.parse(opened, NOW)["MountainAreas"][0]["Lifts"]
    assert [lift["StatusEnglish"] for lift in lifts[:3]] == ["open", "open", "closed"]
    held = wisp.parse(page(LIFT_CLOSED, "<td data-title=\"Status\" class=\"hold\">on hold</td>", 1), NOW)
    assert held["MountainAreas"][0]["Lifts"][0]["Status"] == "On hold"
    # A run's status is a picture: it is read from the name of its cell.
    run = wisp.parse(page(RUN_CLOSED, "<td data-title=\"Status\" class=\"open\"><img", 1), NOW)
    trail = run["MountainAreas"][1]["Trails"][0]
    assert (trail["Name"], trail["Status"], trail["StatusEnglish"]) == ("Happy Camper", "Open", "open")


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="Happy Camper has difficulty symbols \\['teal'\\]"):
        wisp.parse(page("/themes/pgri/images/green.svg", "/themes/pgri/images/teal.svg", 1), NOW)
    with pytest.raises(ValueError, match="has the status '', not a word"):
        wisp.parse(page(RUN_CLOSED, "<td data-title=\"Status\"><img", 1), NOW)
    with pytest.raises(ValueError, match="not a run name and a status"):
        wisp.parse(page("<td data-title=\"Run Name\">", "<td data-title=\"Trail\">", 1), NOW)
    with pytest.raises(ValueError, match="the page's lifts were not found"):
        wisp.parse(page("<section class=\"lift-section lift-section-main\"", "<section class=\"lifts\""), NOW)
    with pytest.raises(ValueError, match="the page's runs were not found"):
        wisp.parse(page("lift-section-main slopes-section", "slopes-section"), NOW)
    with pytest.raises(ValueError, match="the page's lifts were not found"):
        wisp.parse("<html><body>Page not found</body></html>", NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = wisp.parse(figure(PAGE, "Current Base", "deep"), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 4
