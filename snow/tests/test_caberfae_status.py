from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import caberfae

# The page with its scripts, styles, menus, written comments, lift hours and footer taken out; the reader gives
# the same on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "caberfae.html").read_text()
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)
# The icon font's cross and check mark, as the page writes them.
CLOSED, OPEN = "data-av_icon=''", "data-av_icon=''"


def page(old: str, new: str, count: int = -1) -> str:
    assert old in PAGE
    return PAGE.replace(old, new, count)


def test_the_preseason_mountain_reads_its_lifts_and_trails():
    # Caberfae's page on 2026-11-26, before it opened: five lifts and 27 trails, every one with the cross.
    feed = caberfae.parse(PAGE, NOW)
    assert feed["Name"] == "Caberfae Peaks" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Caberfae Peaks", 5, 27)]
    lifts, trails = feed["MountainAreas"][0]["Lifts"], feed["MountainAreas"][0]["Trails"]
    assert [lift["Name"] for lift in lifts] == [
        "EAST PEAK TRIPLE CHAIR", "VISTA 1561’ TRIPLE CHAIR", "SOUTH PEAK TRIPLE CHAIR", "NORTH PEAK QUAD CHAIR",
        "GREEN MOUNTAIN FLYING CARPET"]
    assert lifts[0] == {"Name": "EAST PEAK TRIPLE CHAIR", "Status": "Closed", "StatusEnglish": "closed",
                        "Difficulty": None}
    # The page does not say a trail's difficulty: its colour is in the site's stylesheet.
    assert trails[0] == {"Name": "SMILING IRISHMEN", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": ""}
    assert (trails[7]["Name"], trails[17]["Name"], trails[-1]["Name"]) == ("CANYON", "GG’S RIDE", "I-75")
    assert {row["StatusEnglish"] for row in lifts + trails} == {"closed"}


def test_the_snow_report_gives_the_depth_the_snowfall_and_the_day_it_was_written():
    snow = caberfae.parse(PAGE, NOW)["SnowReport"]
    # "Today's Date: NOVEMBER 25, 2026", read as noon in Eastern time, five hours behind UTC in November.
    assert snow["LastUpdate"] == "2026-11-25T17:00:00Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": 0, "Last24HoursIn": 1, "Last48HoursIn": 1,
                                "Last72HoursIn": 1}
    assert snow["SeasonTotalIn"] == 1 and snow["BaseConditions"] == "Getting ready to make snow!"
    ranged = caberfae.parse(page("SNOW BASE &#8211; 0&#8243;", "SNOW BASE &#8211; 12-30&#8243;"), NOW)
    assert (ranged["SnowReport"]["BaseArea"]["BaseMinIn"], ranged["SnowReport"]["BaseArea"]["BaseMaxIn"]) == (12, 30)


def test_a_check_mark_is_an_open_lift_or_trail_and_the_page_s_counts_have_to_agree():
    opened = page(CLOSED, OPEN, 2).replace("LIFTS OPEN &#8211; 0/5", "LIFTS OPEN &#8211; 2/5")
    lifts = caberfae.parse(opened, NOW)["MountainAreas"][0]["Lifts"]
    assert [lift["StatusEnglish"] for lift in lifts] == ["open", "open", "closed", "closed", "closed"]
    assert lifts[0]["Status"] == "Open"
    at = PAGE.index(CLOSED, PAGE.index("TRAIL STATUS"))
    opened = (PAGE[:at] + OPEN + PAGE[at + len(CLOSED):]).replace("SLOPES OPEN &#8211; 0/27",
                                                                 "SLOPES OPEN &#8211; 1/27")
    trails = caberfae.parse(opened, NOW)["MountainAreas"][0]["Trails"]
    assert [trail["Name"] for trail in trails if trail["StatusEnglish"] == "open"] == ["SMILING IRISHMEN"]
    # A check mark the page's own count does not own up to means the icons no longer mean what the reader thinks.
    with pytest.raises(ValueError, match="lifts open reads '0/5' but 2 of 5 were read"):
        caberfae.parse(page(CLOSED, OPEN, 2), NOW)


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="EAST PEAK TRIPLE CHAIR's icon is '\\\\ue814' of entypo-fontello"):
        caberfae.parse(page(CLOSED, "data-av_icon=''", 1), NOW)
    with pytest.raises(ValueError, match="icon is '\\\\ue813' of fontawesome"):
        caberfae.parse(page("data-av_iconfont='entypo-fontello'", "data-av_iconfont='fontawesome'", 1), NOW)
    with pytest.raises(ValueError, match="slopes open reads '0/28' but 0 of 27 were read"):
        caberfae.parse(page("SLOPES OPEN &#8211; 0/27", "SLOPES OPEN &#8211; 0/28"), NOW)
    with pytest.raises(ValueError, match="lists 5 lifts or trails under a heading but 4 were read"):
        caberfae.parse(page("<span class='iconlist-char'", "<span class='icon-char'", 1), NOW)
    with pytest.raises(ValueError, match="the lift status and the trail status were not found"):
        caberfae.parse(page(">TRAIL STATUS</h2>", ">SLOPES</h2>"), NOW)
    with pytest.raises(ValueError, match="were not found"):
        caberfae.parse("<html><body>Page not found</body></html>", NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = caberfae.parse(page("SNOW BASE &#8211; 0&#8243;", "SNOW BASE &#8211; thin"), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"][0]["Lifts"]) == 5
    assert "SnowReport" not in caberfae.parse(page("Today’s Date: NOVEMBER 25, 2026", "Today"), NOW)
