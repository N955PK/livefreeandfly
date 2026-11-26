from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import timberlinewv

# The page with its scripts, styles, menus, written report and footer taken out; the reader gives the same on the
# whole page.
PAGE = (Path(__file__).parent / "fixtures" / "timberlinewv.html").read_text()
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)
IMAGES = "https://timberlinemountain.com/wp-content/plugins/ski-area-snow-report/public/images/"
CLOSED = f"<img decoding=\"async\" class=\"status-icon\" src=\"{IMAGES}red-x-32.png\"> Closed"
# The page has shown no open line yet, so the name of this icon is made up: the reader does not depend on it.
OPEN = f"<img decoding=\"async\" class=\"status-icon\" src=\"{IMAGES}green-check-32.png\"> Open"


def page(old: str, new: str, count: int = -1) -> str:
    assert old in PAGE
    return PAGE.replace(old, new, count)


def test_the_closed_mountain_reads_its_lifts_its_trails_and_its_terrain_parks():
    # Timberline's page on 2026-11-26, before it opened: four lifts, 20 trails and two parks, all closed.
    feed = timberlinewv.parse(PAGE, NOW)
    assert feed["Name"] == "Timberline Mountain" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Timberline Mountain", 4, 0), ("Trails", 0, 20), ("Terrain Parks", 0, 2)]
    lifts = feed["MountainAreas"][0]["Lifts"]
    assert [lift["Name"] for lift in lifts] == ["First Flurries Carpets", "6-Person Chair", "Quad Chair",
                                                "Thunder Snow Rope Tow"]
    assert lifts[0] == {"Name": "First Flurries Carpets", "Status": "Closed", "StatusEnglish": "closed",
                        "Difficulty": None}
    trails = {trail["Name"]: trail for trail in feed["MountainAreas"][1]["Trails"]}
    assert trails["Bear Stroll"] == {"Name": "Bear Stroll", "Status": "Closed", "StatusEnglish": "closed",
                                     "Difficulty": "Green"}
    assert (trails["Twister"]["Difficulty"], trails["White Lightning"]["Difficulty"],
            trails["The Drop"]["Difficulty"]) == ("Blue", "Black", "Double black")
    # A terrain park is given no difficulty.
    assert feed["MountainAreas"][2]["Trails"] == [
        {"Name": "Snow Squall", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": ""},
        {"Name": "Thunder Snow", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": ""}]
    rows = [row for area in feed["MountainAreas"] for row in area["Lifts"] + area["Trails"]]
    assert {row["StatusEnglish"] for row in rows} == {"closed"}


def test_the_snow_report_is_undated_and_gives_the_depth_as_a_low_and_a_high():
    snow = timberlinewv.parse(PAGE, NOW)["SnowReport"]
    # The page does not say when its figures were written; out of season they are all noughts.
    assert snow["LastUpdate"] is None and snow["Resortwide"] is True and snow["BaseConditions"] is None
    assert snow["BaseArea"] == {"Name": "Mountain", "Last24HoursIn": 0, "Last7DaysIn": 0, "BaseMinIn": 0,
                                "BaseMaxIn": 0}
    filled = page("<p class=\"resort-info-title\">Base Hi</p>\n                        <p>0 in</p>",
                  "<p class=\"resort-info-title\">Base Hi</p>\n                        <p>36.5 in</p>")
    assert timberlinewv.parse(filled, NOW)["SnowReport"]["BaseArea"]["BaseMaxIn"] == 36.5


def test_an_open_lift_and_trail_are_read_in_the_page_s_words():
    feed = timberlinewv.parse(page(CLOSED, OPEN, 5), NOW)
    assert [lift["StatusEnglish"] for lift in feed["MountainAreas"][0]["Lifts"]] == ["open"] * 4
    trails = feed["MountainAreas"][1]["Trails"]
    assert (trails[0]["Name"], trails[0]["Status"], trails[1]["Status"]) == ("Bear Stroll", "Open", "Closed")
    held = timberlinewv.parse(page(CLOSED, OPEN.replace("> Open", "> Wind hold"), 1), NOW)
    assert held["MountainAreas"][0]["Lifts"][0]["Status"] == "Wind hold"


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="First Flurries Carpets's status icon is red-x-32 but it reads 'Open'"):
        timberlinewv.parse(page(CLOSED, CLOSED.replace("> Closed", "> Open"), 1), NOW)
    with pytest.raises(ValueError, match="status icon is green-check-32 but it reads 'Closed'"):
        timberlinewv.parse(page(CLOSED, OPEN.replace("> Open", "> Closed"), 1), NOW)
    with pytest.raises(ValueError, match="Bear Stroll has a difficulty symbol the reader does not know: novice"):
        timberlinewv.parse(page(f"{IMAGES}beginner.png", f"{IMAGES}novice.png", 1), NOW)
    with pytest.raises(ValueError, match="26 lines of lifts and trails but 25 were read"):
        timberlinewv.parse(page("class=\"status-icon\"", "class=\"icon\"", 1), NOW)
    with pytest.raises(ValueError, match="a kind of line the reader does not know: glade"):
        timberlinewv.parse(page("<p class=\"trail-access-name\">", "<p class=\"glade-access-name\">", 1), NOW)
    with pytest.raises(ValueError, match="the page lists no lifts or no trails"):
        timberlinewv.parse("<html><body>Page not found</body></html>", NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = timberlinewv.parse(page("<p class=\"resort-info-title\">Base Lo</p>", "<p class=\"title\">Base Lo</p>"),
                              NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 3
