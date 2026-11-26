from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import spiritmtn

# The page's trails and lifts with its scripts, styles, menus and layout settings taken out; the reader gives the
# same on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "spiritmtn.html").read_text()
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)
CLOSED = '<span class="trail-status trail-status-closed">Closed</span>'


def changed(old: str, new: str, count: int = -1) -> str:
    assert old in PAGE
    return PAGE.replace(old, new, count)


def test_the_preseason_mountain_reads_its_lifts_and_trails():
    # Spirit Mountain's page on 2026-11-26, two days before opening: five lifts and 23 trails, none open.
    feed = spiritmtn.parse(PAGE, NOW)
    assert feed["Name"] == "Spirit Mountain" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    assert "SnowReport" not in feed and [area["Name"] for area in feed["MountainAreas"]] == ["Spirit Mountain"]
    area = feed["MountainAreas"][0]
    assert [(lift["Name"], lift["Status"]) for lift in area["Lifts"]] == [
        ("Prospector Carpet", "Closed"), ("Highline Chair", "Closed"), ("Big Air Chair", "Closed"),
        ("Lone Oak Tow Rope", "Closed for season"), ("Spirit Express II", "Closed for season")]
    assert area["Lifts"][3] == {"Name": "Lone Oak Tow Rope", "Status": "Closed for season",
                                "StatusEnglish": "closed for season", "Difficulty": None}
    trails = {trail["Name"]: trail for trail in area["Trails"]}
    assert len(trails) == 23 and {trail["StatusEnglish"] for trail in trails.values()} == {"closed"}
    assert trails["Sour Dough Sam"] == {"Name": "Sour Dough Sam", "Status": "Closed", "StatusEnglish": "closed",
                                        "Difficulty": "Green"}
    assert trails["Timber Cruiser"]["Difficulty"] == "Blue" and trails["Summit Chute"]["Difficulty"] == "Black"
    # A terrain park has no difficulty.
    assert trails["Spirit Park (Big Park)"]["Difficulty"] == ""
    assert [sum(trail["Difficulty"] == level for trail in trails.values())
            for level in ("Green", "Blue", "Black", "")] == [7, 8, 5, 3]


def test_an_open_trail_and_an_open_lift_are_read():
    # The first status on the page is Sour Dough Sam's; the items' own classes are not what is read.
    page = changed(CLOSED, '<span class="trail-status trail-status-open">Open</span>', 1)
    area = spiritmtn.parse(page, NOW)["MountainAreas"][0]
    assert area["Trails"][0]["StatusEnglish"] == "open" and area["Trails"][1]["StatusEnglish"] == "closed"
    head, lifts = PAGE.split("type-lift", 1)
    page = head + "type-lift" + lifts.replace(CLOSED, '<span class="trail-status trail-status-open">Open</span>', 1)
    lift = spiritmtn.parse(page, NOW)["MountainAreas"][0]["Lifts"][0]
    assert lift == {"Name": "Prospector Carpet", "Status": "Open", "StatusEnglish": "open", "Difficulty": None}


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="is marked shut but reads 'Closed'"):
        spiritmtn.parse(changed(CLOSED, '<span class="trail-status trail-status-shut">Closed</span>', 1), NOW)
    with pytest.raises(ValueError, match="a difficulty the reader does not know: extreme"):
        spiritmtn.parse(changed("trail-difficulty-most-difficult", "trail-difficulty-extreme", 1), NOW)
    with pytest.raises(ValueError, match="28 statuses but 5 lifts and 22 trails"):
        spiritmtn.parse(changed("type-trail", "type-run", 1), NOW)
    with pytest.raises(ValueError, match="not a name and a status"):
        spiritmtn.parse(changed('<span class="trail-status trail-status-closed">',
                                '<span class="status closed">', 1), NOW)
    with pytest.raises(ValueError):
        spiritmtn.parse("<html><body>Not the page</body></html>", NOW)
