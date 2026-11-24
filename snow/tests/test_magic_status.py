from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import magic

FIXTURES = Path(__file__).parent / "fixtures"
# The two reads of Magic's snow report page on 2026-11-24, each cut down to the script element its records are in.
PAGES = {"status": (FIXTURES / "magic.html").read_text(), "more": (FIXTURES / "magic_page2.html").read_text()}
# The page's first read as the Internet Archive kept it on 2026-02-05, in season, cut down the same way.
OPEN = (FIXTURES / "magic_open_2026-02-05.html").read_text()
NOW = datetime(2026, 11, 24, 17, 0, tzinfo=timezone.utc)


def test_the_closed_mountain_reads_as_every_lift_and_trail_closed_by_difficulty():
    # Before it opened: five lifts, and 54 trails over the two reads of the page, all closed.
    feed = magic.parse(PAGES, NOW)
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Magic Mountain", 5, 0), ("Easiest", 0, 15), ("More Difficult", 0, 16), ("Most Difficult", 0, 9),
        ("Experts Only", 0, 14)]
    # A lift's name is given without the length the page ends it with ("Red Summit Chair 5,400'").
    assert [lift["Name"] for lift in feed["MountainAreas"][0]["Lifts"]] == [
        "Red Summit Chair", "Black Summit Quad", "Green Mid-Mtn Chair", "Abracadabra Area Tow", "Learn-to-Ski Lift"]
    rows = [row for area in feed["MountainAreas"] for row in area["Lifts"] + area["Trails"]]
    assert {row["StatusEnglish"] for row in rows} == {"closed"} and all(row["Name"] for row in rows)
    assert feed["MountainAreas"][4]["Trails"][-1] == {"Name": "Pitch Black", "Status": "Closed", "StatusEnglish": "closed",
                                                      "Difficulty": "Double black", "Grooming": "No"}


def test_the_snow_report_has_snowfall_and_no_base_depth():
    snow = magic.parse(PAGES, NOW)["SnowReport"]
    assert snow["LastUpdate"] == "2026-11-24T16:43:01Z" and snow["SeasonTotalIn"] == 3
    assert snow["BaseArea"] == {"Name": "Mountain", "Last24HoursIn": 0, "Last48HoursIn": 0, "Last7DaysIn": 0}
    # The day's report, without the standing explanation the page opens with.
    assert snow["Report"].startswith("November 24 Report:")


def test_a_check_mark_reads_as_open_and_as_groomed():
    records, totals = magic.collections(OPEN)
    assert totals["Lift Status"] == 5 and totals["Green Trail Status"] == 15
    lifts = {lift["liftStatus"]: magic.status_row("Lift", lift.get("open"), None)["StatusEnglish"]
             for lift in records["Lift Status"].values()}
    assert lifts["Red Summit Chair 5,400'"] == "closed" and lifts["Black Summit Quad 5,200'"] == "open"
    assert sum(state == "open" for state in lifts.values()) == 3
    trails = {trail["title"]: magic.trail_row(trail, "Green") for trail in records["Green Trail Status"].values()}
    assert trails["Wand"] == {"Name": "Wand", "Status": "Open", "StatusEnglish": "open", "Difficulty": "Green",
                              "Grooming": "Yes"}
    assert trails["Kinderspiel"]["StatusEnglish"] == "open" and trails["Kinderspiel"]["Grooming"] == "No"
    assert magic.status_row("Lift", "Wind hold", None)["StatusEnglish"] == "wind hold"
    assert magic.inches('73"') == 73 and magic.inches("") is None


def test_a_page_whose_records_do_not_add_up_is_refused():
    # The first read alone has twelve of the fifteen easiest trails.
    with pytest.raises(ValueError, match="Green Trail Status counts 15 records but 12"):
        magic.parse({"status": PAGES["status"], "more": PAGES["status"]}, NOW)
    with pytest.raises(ValueError, match="records were not found"):
        magic.parse({"status": "<html></html>", "more": PAGES["more"]}, NOW)
