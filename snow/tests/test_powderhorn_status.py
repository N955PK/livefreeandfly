from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import powderhorn

# The page's snowfall, lift status and trail status with its scripts, styles and menus taken out; the reader gives
# the same on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "powderhorn.html").read_text()
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)
DASH = '<p class="pgri-stat-n has-text-align-center wp-block-paragraph">—</p>'
CLOSED = '<span class="pgri-groom__lbl">Closed</span>'
COUNT = "<strong>0</strong> of <strong>56</strong> runs open"


def changed(old: str, new: str, count: int = -1) -> str:
    assert old in PAGE
    return PAGE.replace(old, new, count)


def figures(*said: str) -> str:
    """The page with its snow figures written in, in the page's order: 24 and 48 hours, 7 days, base, season."""
    page = PAGE
    for value in said:
        assert DASH in page
        page = page.replace(DASH, DASH.replace("—", value), 1)
    return page


def test_the_preseason_mountain_reads_each_part_with_its_lifts_and_runs():
    # Powderhorn's page on 2026-11-26, before opening: five lifts and 56 runs, none open.
    feed = powderhorn.parse(PAGE, NOW)
    assert feed["Name"] == "Powderhorn" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    assert [(area["Name"], [lift["Name"] for lift in area["Lifts"]], len(area["Trails"]))
            for area in feed["MountainAreas"]] == [
        ("West End", ["Wild West Express"], 21),
        ("Beginner", ["Explorer Conveyor", "Easy Rider", "Discovery Conveyor"], 11),
        ("Flat Top Flyer", ["Flat Top Flyer"], 24)]
    assert feed["MountainAreas"][0]["Lifts"] == [{"Name": "Wild West Express", "Status": "Closed",
                                                  "StatusEnglish": "closed", "Difficulty": None}]
    trails = {trail["Name"]: trail for area in feed["MountainAreas"] for trail in area["Trails"]}
    assert len(trails) == 56
    assert trails["Whistle Pup"] == {"Name": "Whistle Pup", "Status": "Closed", "StatusEnglish": "closed",
                                     "Difficulty": "Green"}
    # A run the page has set no status for is carried in the page's words, and no run is groomed yet.
    assert trails["Boardwalk"]["Status"] == "Not yet set" and trails["Boardwalk"]["StatusEnglish"] == "not yet set"
    assert {trail["StatusEnglish"] for trail in trails.values()} == {"closed", "not yet set"}
    assert not any("Grooming" in trail for trail in trails.values())
    # A terrain park is read without its mark, with the difficulty the page gives it.
    assert trails["E–Z Terrain Park"]["Difficulty"] == "Green" and trails["Upper Peace Park"]["Difficulty"] == "Blue"
    assert trails["Cannonball"]["Difficulty"] == "Double black" and trails["Quickdraw"]["Difficulty"] == "Black"
    assert [sum(trail["Difficulty"] == level for trail in trails.values())
            for level in ("Green", "Blue", "Black", "Double black")] == [12, 16, 26, 2]


def test_the_preseason_dashes_are_no_snow_report_and_a_filled_one_is_read():
    assert "SnowReport" not in powderhorn.parse(PAGE, NOW)
    assert powderhorn.parse(figures("2&quot;", "5.5&quot;", "11&quot;", "38&quot;", "97&quot;"), NOW)["SnowReport"] == {
        "LastUpdate": None, "Resortwide": True, "BaseConditions": None, "SeasonTotalIn": 97,
        "BaseArea": {"Name": "Mountain", "Last24HoursIn": 2, "Last48HoursIn": 5.5, "Last7DaysIn": 11, "BaseIn": 38},
        "Report": None, "Alert": None}
    # Without a base depth there is no snow report, and the lifts are still read.
    feed = powderhorn.parse(figures("2&quot;", "5&quot;", "11&quot;"), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 3


def test_open_and_groomed_runs_and_an_open_lift_are_read():
    page = changed(CLOSED, '<span class="pgri-groom__lbl">Groomed</span>', 1)
    page = page.replace(CLOSED, '<span class="pgri-groom__lbl">Open</span>', 1)
    page = page.replace(COUNT, "<strong>2</strong> of <strong>56</strong> runs open")
    page = page.replace('<span class="pgri-clist__pill pgri-clist__pill--closed">Closed</span>',
                        '<span class="pgri-clist__pill pgri-clist__pill--open">Open</span>', 1)
    west, beginner = powderhorn.parse(page, NOW)["MountainAreas"][:2]
    assert west["Lifts"][0] == {"Name": "Wild West Express", "Status": "Open", "StatusEnglish": "open",
                                "Difficulty": None}
    assert beginner["Lifts"][0]["StatusEnglish"] == "closed"
    # A groomed run is an open one, and on a day some run is groomed the others are not.
    assert beginner["Trails"][0] == {"Name": "Whistle Pup", "Status": "Open", "StatusEnglish": "open",
                                     "Difficulty": "Green", "Grooming": "Yes"}
    assert beginner["Trails"][1] == {"Name": "Lower Dude", "Status": "Open", "StatusEnglish": "open",
                                     "Difficulty": "Green", "Grooming": "No"}
    assert beginner["Trails"][2]["StatusEnglish"] == "closed" and beginner["Trails"][2]["Grooming"] == "No"
    hold = changed('<span class="pgri-clist__pill pgri-clist__pill--closed">Closed</span>',
                   '<span class="pgri-clist__pill pgri-clist__pill--hold">Wind Hold</span>', 1)
    lift = powderhorn.parse(hold, NOW)["MountainAreas"][0]["Lifts"][0]
    assert (lift["Status"], lift["StatusEnglish"]) == ("Wind hold", "wind hold")


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="list of lifts was not found"):
        powderhorn.parse(changed("pgri-clist pgri-clist--lifts", "pgri-list"), NOW)
    with pytest.raises(ValueError, match="grooming report or its count of runs was not found"):
        powderhorn.parse(changed(COUNT, "56 runs"), NOW)
    with pytest.raises(ValueError, match="a difficulty symbol the reader does not know: '▲'"):
        powderhorn.parse(changed('aria-hidden="true">■</span>\t\t\t\t\t\t\tUpper Peace Park',
                                 'aria-hidden="true">▲</span>\t\t\t\t\t\t\tUpper Peace Park'), NOW)
    with pytest.raises(ValueError, match="counts 56 runs but 55 were read"):
        powderhorn.parse(changed('<span class="pgri-groom__lbl">', '<span class="label">', 1), NOW)
    with pytest.raises(ValueError, match="counts 0 runs open but 1 were read"):
        powderhorn.parse(changed(CLOSED, '<span class="pgri-groom__lbl">Open</span>', 1), NOW)
    with pytest.raises(ValueError, match="counts 60 runs but 56 were read"):
        powderhorn.parse(changed(COUNT, "<strong>0</strong> of <strong>60</strong> runs open"), NOW)
    with pytest.raises(ValueError, match="not a name and a status"):
        powderhorn.parse(changed('<span class="pgri-clist__pill pgri-clist__pill--closed">', "<span>", 1), NOW)
    with pytest.raises(ValueError):
        powderhorn.parse("<html><body>Not the page</body></html>", NOW)
