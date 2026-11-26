from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import timberline

# The main part of the page with its drawings, scripts and comments taken out; the reader gives the same on the whole
# page.
PAGE = (Path(__file__).parent / "fixtures" / "timberline.html").read_text()
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)
WAITING = "<td><div>Pucci</div></td><td><div class=status__color--red>Waiting for Snow</div></td>"


def page(old: str, new: str) -> str:
    assert old in PAGE
    return PAGE.replace(old, new)


def test_the_page_is_the_resort_s_conditions_page():
    assert timberline.URL == "https://timberlinelodge.com/conditions"


def test_the_mountain_waiting_for_snow_reads_its_eleven_lifts_as_closed_in_the_page_s_words():
    # Timberline's page on 2026-11-26, before it opens: eleven lifts, every one "Waiting for Snow" beside a red dot.
    feed = timberline.parse(PAGE, NOW)
    assert feed["Name"] == "Timberline" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), area["Trails"]) for area in feed["MountainAreas"]] == [
        ("Timberline", 11, [])]
    lifts = feed["MountainAreas"][0]["Lifts"]
    # "Heidi's" has "at Summit Pass" under it, and the parking lots of the second table are not lifts.
    assert [lift["Name"] for lift in lifts] == [
        "Bruno's", "Timber Tiger", "Pucci", "Jeff Flood", "Molly's", "Stormin' Norman", "Magic Mile", "Palmer",
        "Palmer Snowcat", "Summit Pass", "Heidi's"]
    assert lifts[2] == {"Name": "Pucci", "Status": "Waiting for snow", "StatusEnglish": "closed", "Difficulty": None}
    assert {lift["StatusEnglish"] for lift in lifts} == {"closed"}


def test_the_snow_report_gives_the_depth_at_the_lodge_and_when_it_was_updated():
    snow = timberline.parse(PAGE, NOW)["SnowReport"]
    # "Updated November 26, 6:05am", eight hours behind UTC in November, in the year of the reading.
    assert snow["LastUpdate"] == "2026-11-26T14:05:00Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Lodge (6,000 ft)", "Last24HoursIn": 0, "Last72HoursIn": 0, "BaseIn": 6}
    assert snow["SeasonTotalIn"] == 24 and snow["BaseConditions"] is None
    assert snow["Report"].startswith("Timberline is Closed for Skiing & Snowboarding: We plan to open")


def test_a_date_later_in_the_year_than_the_reading_is_last_year_s():
    january = datetime(2027, 1, 2, 18, 0, tzinfo=timezone.utc)
    assert timberline.parse(PAGE, january)["SnowReport"]["LastUpdate"] == "2026-11-26T14:05:00Z"
    new_year = page("Updated November 26, 6:05am", "Updated December 31, 4:30pm")
    assert timberline.parse(new_year, january)["SnowReport"]["LastUpdate"] == "2027-01-01T00:30:00Z"


def test_a_green_lift_is_open_and_a_yellow_one_keeps_the_page_s_words():
    turning = page(WAITING, "<td><div>Pucci</div></td><td><div class=status__color--green>Open</div></td>")
    turning = turning.replace("<td><div>Magic Mile</div></td><td><div class=status__color--red>Waiting for Snow</div>",
                              "<td><div>Magic Mile</div></td><td><div class=status__color--yellow>Wind Hold</div>")
    turning = turning.replace("<td><div>Palmer</div></td><td><div class=status__color--red>Waiting for Snow</div>",
                              "<td><div>Palmer</div></td><td><div class=\"status__color--green\">Open for Race "
                              "Training</div>")
    lifts = {lift["Name"]: lift for lift in timberline.parse(turning, NOW)["MountainAreas"][0]["Lifts"]}
    assert lifts["Pucci"] == {"Name": "Pucci", "Status": "Open", "StatusEnglish": "open", "Difficulty": None}
    assert (lifts["Magic Mile"]["Status"], lifts["Magic Mile"]["StatusEnglish"]) == ("Wind hold", "wind hold")
    assert (lifts["Palmer"]["Status"], lifts["Palmer"]["StatusEnglish"]) == ("Open for race training", "open")
    assert sum(lift["StatusEnglish"] == "open" for lift in lifts.values()) == 2


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    for changed in (page("Updated November 26, 6:05am", "Updated this morning"),
                    page("Base Depth at 6,000'", "Base Depth at 7,000'"),
                    page("<div class=conditions__item-data>6<span", "<div class=conditions__item-data>15 cm<span")):
        feed = timberline.parse(changed, NOW)
        assert "SnowReport" not in feed and len(feed["MountainAreas"][0]["Lifts"]) == 11


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="0 lift tables"):
        timberline.parse(page("<th scope=col>Lifts</th>", "<th scope=col>Chairs</th>"), NOW)
    with pytest.raises(ValueError, match="0 lift tables"):
        timberline.parse("<html><body>Just a moment...</body></html>", NOW)
    with pytest.raises(ValueError, match="colour the reader does not know"):
        timberline.parse(page(WAITING, WAITING.replace("--red", "--blue")), NOW)
    with pytest.raises(ValueError, match="colour the reader does not know"):
        timberline.parse(page(WAITING, WAITING.replace(" class=status__color--red", "")), NOW)
    with pytest.raises(ValueError, match="Pucci has no status"):
        timberline.parse(page(WAITING, WAITING.replace("Waiting for Snow", "")), NOW)
    with pytest.raises(ValueError, match="has no name"):
        timberline.parse(page(WAITING, WAITING.replace("Pucci", "")), NOW)
    with pytest.raises(ValueError, match="not a name, a status, a type and its hours"):
        timberline.parse(page(WAITING, WAITING + "<td><div>New</div></td>"), NOW)
    with pytest.raises(ValueError, match="lists a lift twice"):
        timberline.parse(page("<td><div>Pucci</div></td>", "<td><div>Palmer</div></td>"), NOW)
