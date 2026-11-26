from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import crystalmi

# The page with its scripts, styles, drawings and comments taken out; the reader gives the same on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "crystalmi.html").read_text()
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)
CLOSED = "<div class=\"closed status-block\">\n Closed\n </div>"
OPEN = "<div class=\"open status-block\">\n Open\n </div>"
NO_TRAILS = "<span class=\"value\">\n 0\n </span>\n <span class=\"f-s-16 total\">/59</span>"
NO_LIFTS = "<span class=\"value\">\n 0\n </span>\n <span class=\"f-s-16 total\">/8</span>"


def page(old: str, new: str, count: int = -1) -> str:
    assert old in PAGE
    return PAGE.replace(old, new, count)


def test_the_closed_mountain_reads_its_lifts_and_the_trails_of_each_part_of_the_mountain():
    # Crystal Mountain's page on 2026-11-26, before it opened: eight lifts and 59 trails, all closed.
    feed = crystalmi.parse(PAGE, NOW)
    assert feed["Name"] == "Crystal Mountain" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Crystal Mountain", 8, 0), ("Buck", 0, 12), ("Crystal Clipper", 0, 6), ("Loki", 0, 11),
        ("Mountain Adventure Zone", 0, 1), ("North Face", 0, 13), ("Backyard", 0, 7), ("Ridge", 0, 9)]
    lifts = feed["MountainAreas"][0]["Lifts"]
    assert lifts[0] == {"Name": "Backyard Triple", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}
    assert [lift["Name"] for lift in lifts[1:3]] == ["Buck Quad", "Crystal Clipper Quad"]
    assert lifts[-1]["Name"] == "Short Carpet"
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    assert {trail["StatusEnglish"] for trail in trails + lifts} == {"closed"}
    assert trails[0] == {"Name": "Giggles", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": "Green",
                         "Grooming": "No"}
    levels = {trail["Name"]: trail["Difficulty"] for trail in trails}
    assert (levels["Cheers To Lou"], levels["Shelburg's Chute"], levels["Ridge Glades"], levels["Jester's Alley"]) == (
        "Blue", "Blue", "Black", "")
    assert set(levels.values()) == {"Green", "Blue", "Black", ""}


def test_the_snow_report_gives_the_base_depth_and_the_day_it_was_written():
    snow = crystalmi.parse(PAGE, NOW)["SnowReport"]
    # "November 26, 2026", read as noon of that day, five hours behind UTC in November.
    assert snow["LastUpdate"] == "2026-11-26T17:00:00Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseMinIn": 0, "BaseMaxIn": 0, "Last24HoursIn": 0}
    assert snow["BaseConditions"] is None and snow["SeasonTotalIn"] is None
    deep = crystalmi.parse(page("0-0&quot;", "18-36&quot;").replace("0&quot;\n", "2.5&quot;\n"), NOW)["SnowReport"]
    assert deep["BaseArea"] == {"Name": "Mountain", "BaseMinIn": 18, "BaseMaxIn": 36, "Last24HoursIn": 2.5}
    assert crystalmi.parse(page("0-0&quot;", "24&quot;"), NOW)["SnowReport"]["BaseArea"]["BaseIn"] == 24


def test_an_open_trail_and_a_held_lift_are_read_in_the_page_s_words():
    # The first rows on the page are Buck's trails.
    opened = page(CLOSED, OPEN, 3).replace(NO_TRAILS, NO_TRAILS.replace(" 0\n", " 3\n"))
    trails = crystalmi.parse(opened, NOW)["MountainAreas"][1]["Trails"]
    assert [trail["StatusEnglish"] for trail in trails[:4]] == ["open", "open", "open", "closed"]
    lift = "<div class=\"lift d-flex ai-center f-s-14 component-row\">\n <div class=\"cell status\">\n "
    held = page(lift + CLOSED, lift + "<div class=\"on-hold status-block\">\n On Hold\n </div>", 1)
    found = crystalmi.parse(held, NOW)["MountainAreas"][0]["Lifts"][0]
    assert (found["Name"], found["Status"], found["StatusEnglish"]) == ("Backyard Triple", "On hold", "on hold")


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="counts 0 of 59 trails open but 1 of 59"):
        crystalmi.parse(page(CLOSED, OPEN, 1), NOW)
    with pytest.raises(ValueError, match="counts 0 of 9 lifts open but 0 of 8"):
        crystalmi.parse(page(NO_LIFTS, NO_LIFTS.replace("/8", "/9")), NOW)
    with pytest.raises(ValueError, match="count of trails was not found"):
        crystalmi.parse(page("Trails Open", "Runs Open"), NOW)
    with pytest.raises(ValueError, match="difficulty symbol the reader does not know: expert"):
        crystalmi.parse(page("level_category advanced", "level_category expert"), NOW)
    with pytest.raises(ValueError, match="not a status, a symbol and a name"):
        crystalmi.parse(page("<div class=\"cell status\">", "<div class=\"cell state\">", 1), NOW)
    with pytest.raises(ValueError, match="no lifts or no trails"):
        crystalmi.parse("<html><body>Page not found</body></html>", NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = crystalmi.parse(page("0-0&quot;", "deep"), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 8
    assert "SnowReport" not in crystalmi.parse(page("<h2>November 26, 2026</h2>", "<h2>Today</h2>"), NOW)
