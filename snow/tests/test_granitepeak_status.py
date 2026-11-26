from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import granitepeak

FIXTURES = Path(__file__).parent / "fixtures"
# Both pages with their scripts, styles, drawings, menus and written report taken out; the reader gives the same
# on the whole pages.
PAGES = {name: (FIXTURES / f"granitepeak_{name}.html").read_text() for name in granitepeak.URLS}
NOW = datetime(2026, 11, 26, 17, 0, tzinfo=timezone.utc)
LIFT_CLOSED = "<div class=\"f-icon icon-closed\" title=\"closed\"></div></div>Blitzen</div>"
RUN_CLOSED = "<div class=\"f-icon icon-closed\"\n             title=\"Closed\"></div>"


def lifts_page(old: str, new: str, count: int = -1) -> dict:
    assert old in PAGES["lifts"]
    return {**PAGES, "lifts": PAGES["lifts"].replace(old, new, count)}


def snow_page(old: str, new: str) -> dict:
    assert old in PAGES["snow"]
    return {**PAGES, "snow": PAGES["snow"].replace(old, new)}


def test_the_mountain_the_day_before_it_opens_reads_each_lift_with_the_runs_it_serves():
    # Granite Peak's pages on 2026-11-26, the day before it opened: seven lifts and 68 runs, three expected.
    feed = granitepeak.parse(PAGES, NOW)
    assert feed["Name"] == "Granite Peak" and feed["LastUpdate"] == "2026-11-26T17:00:00Z"
    # The page lists Meadows, Mystery and Whitetail under Blitzen and again under Santa: they are read once.
    assert [(area["Name"], area["Lifts"][0]["Status"], len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Comet 6-Pack", "Unknown", 12), ("Blitzen", "Closed", 17), ("Santa", "Closed", 2),
        ("Frosty Carpet", "Closed", 1), ("Blizzard Carpet", "Unknown", 1), ("Cupid Quad", "Closed", 15),
        ("Dasher Quad", "Closed", 20)]
    assert all([lift["Name"] for lift in area["Lifts"]] == [area["Name"]] for area in feed["MountainAreas"])
    # The page gives the Comet a bare "17" where its status should be: it is carried as unknown, not guessed.
    assert feed["MountainAreas"][0]["Lifts"] == [{"Name": "Comet 6-Pack", "Status": "Unknown",
                                                  "StatusEnglish": "unknown", "Difficulty": None}]
    assert [trail["Name"] for trail in feed["MountainAreas"][2]["Trails"]] == ["Adios", "Snowflake"]
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    assert len(trails) == 68 == len({trail["Name"] for trail in trails})
    # "Projected" is the page's word for a run it expects to open.
    assert trails[0] == {"Name": "Lower Dusky", "Status": "Expected", "StatusEnglish": "expected",
                         "Difficulty": "Green", "Grooming": "Yes"}
    assert [trail["Name"] for trail in trails if trail["StatusEnglish"] != "closed"] == [
        "Lower Dusky", "Miracle", "Hot Cocoa"]
    assert {trail["Difficulty"] for trail in trails} == {"Green", "Blue", "Black", "Double black", ""}


def test_the_snow_report_gives_the_depth_and_when_it_was_updated():
    snow = granitepeak.parse(PAGES, NOW)["SnowReport"]
    # "Nov 26th - 10:52am" in Central time, six hours behind UTC in November, in the year of the reading.
    assert snow["LastUpdate"] == "2026-11-26T16:52:00Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Mountain", "Last24HoursIn": 0, "Last48HoursIn": 0, "Last7DaysIn": 0,
                                "BaseIn": 36}
    assert snow["SeasonTotalIn"] == 0 and snow["BaseConditions"] is None


def test_a_lift_s_status_is_read_from_its_icon():
    for icon, status in (("open", "Open"), ("projected", "Expected"), ("on-hold", "On hold")):
        pages = lifts_page(LIFT_CLOSED, LIFT_CLOSED.replace("icon-closed", f"icon-{icon}").replace(
            "title=\"closed\"", f"title=\"{icon.replace('-', ' ')}\""))
        lift = granitepeak.parse(pages, NOW)["MountainAreas"][1]["Lifts"][0]
        assert (lift["Name"], lift["Status"], lift["StatusEnglish"]) == ("Blitzen", status, status.lower())


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="counts of lifts and trails were not found"):
        granitepeak.parse(lifts_page("snow-weather page mountain-stats", "snow-weather page"), NOW)
    with pytest.raises(ValueError, match="counts 8 lifts but 7 were read"):
        granitepeak.parse(lifts_page("<span class=\"unit\">/7</span>", "<span class=\"unit\">/8</span>"), NOW)
    with pytest.raises(ValueError, match="counts 72 trails and has 71 rows but 71 were read"):
        granitepeak.parse(lifts_page("<span class=\"unit\">/62</span>", "<span class=\"unit\">/63</span>"), NOW)
    with pytest.raises(ValueError, match="Blitzen's status icon is shut, not one the reader knows"):
        granitepeak.parse(lifts_page(LIFT_CLOSED, LIFT_CLOSED.replace("icon-closed", "icon-shut").replace(
            "title=\"closed\"", "title=\"shut\"")), NOW)
    with pytest.raises(ValueError, match="Blitzen's status icon is open and reads 'closed'"):
        granitepeak.parse(lifts_page(LIFT_CLOSED, LIFT_CLOSED.replace("icon-closed", "icon-open")), NOW)
    with pytest.raises(ValueError, match="not a lift, its status and its runs"):
        granitepeak.parse(lifts_page("component-row lift-title", "component-row", 1), NOW)
    with pytest.raises(ValueError, match="has lists the reader does not know"):
        granitepeak.parse(lifts_page("<h2 class=\"h4 \">Trails</h2>", "<h2 class=\"h4 \">Glades</h2>", 1), NOW)
    with pytest.raises(ValueError, match="Lower Dusky has a difficulty the reader does not know: novice"):
        granitepeak.parse(lifts_page("cell f-icon level icon-beginner", "cell f-icon level icon-novice", 1), NOW)
    # Meadows is listed under two lifts: its statuses there have to agree.
    at = PAGES["lifts"].index(RUN_CLOSED, PAGES["lifts"].index("Meadows\n"))
    pages = {**PAGES, "lifts": PAGES["lifts"][:at] + RUN_CLOSED.replace("icon-closed", "icon-open").replace(
        "\"Closed\"", "\"Open\"") + PAGES["lifts"][at + len(RUN_CLOSED):]}
    with pytest.raises(ValueError, match="Meadows is listed under two lifts with different statuses"):
        granitepeak.parse(pages, NOW)
    with pytest.raises(ValueError):
        granitepeak.parse({**PAGES, "lifts": "<html><body>Page not found</body></html>"}, NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = granitepeak.parse(snow_page("Nov 26th - 10:52am", "this morning"), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 7
