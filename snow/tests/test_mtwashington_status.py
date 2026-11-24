from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import mtwashington

# The page with its scripts, styles, drawings and comments taken out; the reader gives the same on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "mtwashington.html").read_text()
NOW = datetime(2026, 11, 25, 0, 30, tzinfo=timezone.utc)
CLOSED = "<span class=\"pgri-clist__pill pgri-clist__pill--closed\">Closed</span>"
OPEN = "<span class=\"pgri-clist__pill pgri-clist__pill--open\">Open</span>"


def page(old: str, new: str, count: int = -1) -> str:
    assert old in PAGE
    return PAGE.replace(old, new, count)


def test_the_closed_mountain_reads_its_lifts_and_the_runs_of_each_part_of_the_mountain():
    # Mount Washington's page on 2026-11-24, before it opened: ten lifts and 97 runs, all closed.
    feed = mtwashington.parse(PAGE, NOW)
    assert feed["Name"] == "Mount Washington" and feed["LastUpdate"] == "2026-11-25T00:30:00Z"
    # The Nordic, snowshoe and fat bike trails are left out.
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Mount Washington", 10, 0), ("Eagle", 0, 21), ("Hawk", 0, 16), ("Boomerang", 0, 26), ("Easy Acres", 0, 7),
        ("Whiskey Jack", 0, 8), ("Sunrise", 0, 19)]
    lifts = feed["MountainAreas"][0]["Lifts"]
    # The page lists the Boomerang Quad twice: it is read once.
    assert [lift["Name"] for lift in lifts] == [
        "Training Carpet", "Tube Carpet", "Hawk 6 Pack", "Boomerang Quad", "Whiskey Jack", "Sunrise Quad",
        "Lower Carpet", "Mid Carpet", "Upper Carpet", "Eagle Quad"]
    assert lifts[2] == {"Name": "Hawk 6 Pack", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}
    assert {lift["StatusEnglish"] for lift in lifts} == {"closed"}
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    assert len(trails) == 97 and {trail["StatusEnglish"] for trail in trails} == {"closed"}
    assert trails[0] == {"Name": "Linton's Loop", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": "Blue"}
    assert trails[-1]["Name"] == "Rick's Ride Upper" and trails[-1]["Difficulty"] == "Black"
    assert {trail["Difficulty"] for trail in trails} == {"Green", "Blue", "Black", "Double black"}


def test_the_snow_report_gives_the_base_depth_in_inches_and_when_it_was_updated():
    snow = mtwashington.parse(PAGE, NOW)["SnowReport"]
    # "Updated November 24, 2026 7:34 am" in Vancouver, seven hours behind UTC since British Columbia stopped
    # changing its clocks in 2026.
    assert snow["LastUpdate"] == "2026-11-24T14:34:00Z" and snow["Resortwide"] is True
    # 115 cm of base, and the page gives the same 115 as the snow of the last 24 hours.
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": 45.3, "Last24HoursIn": 45.3}
    assert snow["BaseConditions"] is None and snow["Report"].startswith("This storm is a wild one!")


def test_an_open_lift_and_run_are_read_in_the_page_s_words():
    opened = page(CLOSED, OPEN, 3).replace("<strong>0 / 10</strong>", "<strong>3 / 10</strong>")
    feed = mtwashington.parse(opened, NOW)
    assert [lift["StatusEnglish"] for lift in feed["MountainAreas"][0]["Lifts"]][:4] == ["open", "open", "open",
                                                                                         "closed"]
    held = page(CLOSED, "<span class=\"pgri-clist__pill pgri-clist__pill--hold\">On Hold</span>", 1)
    lift = mtwashington.parse(held, NOW)["MountainAreas"][0]["Lifts"][0]
    assert (lift["Name"], lift["Status"], lift["StatusEnglish"]) == ("Training Carpet", "On hold", "on hold")


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="list of lifts was not found"):
        mtwashington.parse(page("pgri-clist--lifts", "pgri-clist--chairs"), NOW)
    with pytest.raises(ValueError, match="list of lifts was not found"):
        mtwashington.parse("<html>Just a moment...</html>", NOW)
    with pytest.raises(ValueError, match="counts 0 of 11 lifts open but 0 of 10"):
        mtwashington.parse(page("<strong>0 / 10</strong>", "<strong>0 / 11</strong>"), NOW)
    with pytest.raises(ValueError, match="counts 0 of 10 lifts open but 1 of 10"):
        mtwashington.parse(page(CLOSED, OPEN, 1), NOW)
    with pytest.raises(ValueError, match="counts 98 runs but 97"):
        mtwashington.parse(page("<strong>0 / 97</strong>", "<strong>0 / 98</strong>"), NOW)
    with pytest.raises(ValueError, match="difficulty symbols"):
        mtwashington.parse(page("pgri-clist__diff--double-black", "pgri-clist__diff--triple-black"), NOW)
    # The second Boomerang Quad with a status of its own.
    last = PAGE.rindex(CLOSED, 0, PAGE.index("pgri-clist--trails"))
    with pytest.raises(ValueError, match="Boomerang Quad is listed twice"):
        mtwashington.parse(PAGE[:last] + OPEN + PAGE[last + len(CLOSED):], NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = mtwashington.parse(page("<strong>115 cm</strong>", "<strong>120 cm</strong>"), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"][0]["Lifts"]) == 10
    assert "SnowReport" not in mtwashington.parse(page("Updated November 24, 2026 7:34 am", "Updated this morning"),
                                                  NOW)
    assert "SnowReport" not in mtwashington.parse(page("New Snow · 24h", "New Snow"), NOW)
