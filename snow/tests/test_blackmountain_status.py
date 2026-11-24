from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import blackmountain

# Black Mountain's conditions page on 2026-11-24, before it opened, with its scripts and style sheets taken out
# (they are seven eighths of the page and none of what is read).
PAGE = (Path(__file__).parent / "fixtures" / "blackmountain.html").read_text()
NOW = datetime(2026, 11, 24, 18, 0, tzinfo=timezone.utc)
CLOSED = ('<span style="color:#FF4040;" class="wixui-rich-text__text"><span style="letter-spacing:normal;" '
          'class="wixui-rich-text__text"><span style="font-size:20px;" class="wixui-rich-text__text">Closed</span>')


def with_statuses(page: str, words: dict) -> str:
    """The page with some of its statuses (numbered from 0 in the page's order) changed to other words."""
    parts = page.split(CLOSED)
    assert len(parts) == 68
    return "".join(part + CLOSED.replace("Closed", words.get(n, "Closed")) for n, part in enumerate(parts[:-1])) + parts[-1]


def test_the_closed_mountain_reads_as_every_lift_and_trail_closed_by_kind():
    feed = blackmountain.parse(PAGE, NOW)
    assert feed["Name"] == "Black Mountain" and feed["LastUpdate"] == "2026-11-24T18:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Black Mountain", 5, 0), ("Beginner", 0, 18), ("Intermediate", 0, 18), ("Advanced", 0, 14),
        ("Experts Only", 0, 9), ("Extreme / Hike To Terrain", 0, 3)]
    assert [lift["Name"] for lift in feed["MountainAreas"][0]["Lifts"]] == [
        "Double Chair Summit", "East Bowl Triple", "Platter Pull", "J-Bar", "Fluffy Cow Handle Tow"]
    rows = [row for area in feed["MountainAreas"] for row in area["Lifts"] + area["Trails"]]
    assert {row["StatusEnglish"] for row in rows} == {"closed"} and all(row["Name"] for row in rows)
    assert feed["MountainAreas"][0]["Lifts"][0] == {"Name": "Double Chair Summit", "Status": "Closed",
                                                    "StatusEnglish": "closed", "Difficulty": None}
    assert feed["MountainAreas"][1]["Trails"][0] == {"Name": "Sugarbush", "Status": "Closed", "StatusEnglish": "closed",
                                                     "Difficulty": "Green"}
    assert [area["Trails"][0]["Difficulty"] for area in feed["MountainAreas"][1:]] == [
        "Green", "Blue", "Black", "Double black", "Double black"]


def test_a_run_of_names_takes_the_statuses_after_it_in_order():
    # The lifts are the first five statuses; the first run of trails is six names, then their six statuses.
    feed = blackmountain.parse(with_statuses(PAGE, {1: "Open", 6: "Open", 10: "As Needed"}), NOW)
    lifts = {lift["Name"]: lift["StatusEnglish"] for lift in feed["MountainAreas"][0]["Lifts"]}
    assert lifts["East Bowl Triple"] == "open" and list(lifts.values()).count("closed") == 4
    trails = {trail["Name"]: trail for area in feed["MountainAreas"] for trail in area["Trails"]}
    assert trails["Sugar Loop"]["StatusEnglish"] == "open" and trails["Sugarbush"]["StatusEnglish"] == "closed"
    assert trails["Lower Black Beauty"]["Status"] == "As needed" and trails["Lower Black Beauty"]["StatusEnglish"] == "as needed"


def test_the_snow_report_has_the_page_s_figures_and_words_and_no_base_depth():
    snow = blackmountain.parse(PAGE, NOW)["SnowReport"]
    # The page said "Updated: November 20th 2026", by the day only: noon Eastern. "Trails Open: Closed" is no count.
    assert snow["LastUpdate"] == "2026-11-20T17:00:00Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Mountain", "Last24HoursIn": 0} and snow["SeasonTotalIn"] == 0
    assert snow["BaseConditions"] is None and snow["TotalOpenTrails"] is None and snow["GroomedTrails"] == 0
    assert snow["Report"] == ("<p>Read the letter from the GM - Opening Day Set.</p>"
                              "<p>We will be updating this page throughout the week; stay tuned for updates.</p>")


def test_the_season_s_figures_read_in_inches_and_a_day_without_its_year_is_the_latest_such_day():
    page = PAGE.replace("24-hour Snow Total: 0", "24-hour Snow Total: 2&quot;").replace("Season Snow Total: 0", 'Season Snow Total: 40"')
    page = page.replace("Snow Conditions:&nbsp;", "Snow Conditions: Packed Powder").replace("Trails Open: Closed", "Trails Open: 24")
    snow = blackmountain.parse(page, NOW)["SnowReport"]
    assert snow["BaseArea"]["Last24HoursIn"] == 2 and snow["SeasonTotalIn"] == 40
    assert snow["BaseConditions"] == "Packed Powder" and snow["TotalOpenTrails"] == 24
    assert blackmountain.posted(["Snow Report – Sunday, March 1"], NOW) == "2026-03-01T17:00:00Z"
    assert blackmountain.posted(["Snow Report – Friday, December 18th"], NOW) == "2025-12-18T17:00:00Z"
    assert blackmountain.posted(["Snow Report – Friday, January 16th, 2026"], NOW) == "2026-01-16T17:00:00Z"
    assert blackmountain.posted(["Opening day is December 12"], NOW) is None
    assert blackmountain.inches("Trace") is None


def test_a_page_whose_names_and_statuses_do_not_pair_off_is_refused():
    # A word that is not a status reads as a name, which leaves the run before it short.
    with pytest.raises(ValueError, match="6 names but 2 statuses under BEGINNER"):
        blackmountain.parse(with_statuses(PAGE, {7: "Groomed"}), NOW)
    with pytest.raises(ValueError, match="status was not found"):
        blackmountain.parse(PAGE.replace("Trail &amp; Lift Status", "Status"), NOW)
    with pytest.raises(ValueError, match="no lifts"):
        blackmountain.parse(PAGE.replace(">LIFTS<", ">TOWS<"), NOW)
