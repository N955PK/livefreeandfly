from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import whitefish

# The page with its scripts, styles, menus and drawings taken out, but for the drawings of the trails' difficulty,
# and without the snow reporter's name; the reader gives the same on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "whitefish.html").read_text()
NOW = datetime(2026, 11, 26, 16, 0, tzinfo=timezone.utc)
LIFT_CLOSED = "<img decoding=\"async\" alt=\"Closed\" src=\"/assets/is_closed.svg\" style=\"height:20px; width:auto;\">"
RUN_CLOSED = "<img decoding=\"async\" alt=\"Closed\" src=\"/assets/is_closed.svg\" " \
             "style=\"height:18px; width:auto; display:block;\">"


def changed(old: str, new: str, count: int = -1) -> str:
    assert old in PAGE
    return PAGE.replace(old, new, count)


def pictured(picture: str, word: str) -> str:
    """A status picture saying another word."""
    return picture.replace("Closed", word).replace("is_closed", "is_" + "_".join(word.lower().split()))


def test_the_closed_mountain_reads_each_lift_with_the_trails_under_it():
    # Whitefish's page on 2026-11-26, before it opened: thirteen lifts and 116 trails, all closed.
    feed = whitefish.parse(PAGE, NOW)
    assert feed["Name"] == "Whitefish" and feed["LastUpdate"] == "2026-11-26T16:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Chair 1 - Big Mountain Express", 1, 32), ("Chair 2 - Swift Creek Express", 1, 12),
        ("Chair 3 - Tenderfoot", 1, 5), ("Chair 4 - Snow Ghost Express", 1, 7), ("Chair 5 - East Rim", 1, 10),
        ("Chair 6 - Base Lodge", 1, 3), ("Chair 7 - Big Creek Express", 1, 11), ("Chair 8 - Hellroaring", 1, 14),
        ("Chair 9 - Easy Rider", 1, 2), ("Chair 11 - Flower Point", 1, 7), ("Bigfoot T-Bar 2", 1, 5),
        ("Big Easy Carpet", 1, 1), ("2 Easy Carpet", 1, 1), ("Terrain Parks", 0, 6)]
    assert feed["MountainAreas"][0]["Lifts"] == [{"Name": "Chair 1 - Big Mountain Express", "Status": "Closed",
                                                  "StatusEnglish": "closed", "Difficulty": None}]
    rows = [row for area in feed["MountainAreas"] for row in area["Lifts"] + area["Trails"]]
    assert len(rows) == 129 and {row["StatusEnglish"] for row in rows} == {"closed"}
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    assert len({trail["Name"] for trail in trails}) == 116
    # No trail is called groomed, so none carries grooming.
    assert trails[0] == {"Name": "1000 Turns", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": "Black"}
    # "Cal&#039;s Country" is read as it is said.
    assert trails[5]["Name"] == "Cal's Country"
    assert [sum(trail["Difficulty"] == level for trail in trails)
            for level in ("Green", "Blue", "Black", "Double black")] == [16, 42, 50, 8]


def test_the_snow_report_gives_the_summit_s_depth_and_the_day_of_its_story():
    snow = whitefish.parse(PAGE, NOW)["SnowReport"]
    # "Friday, Nov. 20, 2026", measured around 6 a.m., seven hours behind UTC in November.
    assert snow["LastUpdate"] == "2026-11-20T13:00:00Z" and snow["Resortwide"] is True
    assert snow["SummitArea"] == {"Name": "Summit", "OvernightIn": 0, "Last24HoursIn": 3, "Last7DaysIn": 13,
                                  "BaseIn": 20}
    assert snow["BaseArea"] == {"Name": "Base Area", "Last24HoursIn": 3, "Last7DaysIn": 5, "BaseIn": None}
    assert snow["SeasonTotalIn"] == 31 and snow["BaseConditions"] is None


def test_a_story_with_no_day_leaves_the_report_undated():
    snow = whitefish.parse(changed("<strong>Friday, Nov. 20, 2026:</strong>", "<strong>Good morning!</strong>"),
                           NOW)["SnowReport"]
    assert snow["LastUpdate"] is None and snow["SummitArea"]["BaseIn"] == 20


def test_open_lifts_and_open_and_groomed_trails_are_read():
    page = changed(LIFT_CLOSED, pictured(LIFT_CLOSED, "Open"), 1)
    page = page.replace(LIFT_CLOSED, pictured(LIFT_CLOSED, "On Hold"), 1)
    page = page.replace(RUN_CLOSED, pictured(RUN_CLOSED, "Groomed"), 1)
    page = page.replace(RUN_CLOSED, pictured(RUN_CLOSED, "Open"), 1)
    feed = whitefish.parse(page, NOW)
    lifts = [area["Lifts"][0] for area in feed["MountainAreas"][:3]]
    assert [(lift["Status"], lift["StatusEnglish"]) for lift in lifts] == [
        ("Open", "open"), ("On hold", "on hold"), ("Closed", "closed")]
    trails = feed["MountainAreas"][0]["Trails"]
    assert trails[0] == {"Name": "1000 Turns", "Status": "Open", "StatusEnglish": "open", "Difficulty": "Black",
                         "Grooming": "Yes"}
    assert (trails[1]["StatusEnglish"], trails[1]["Grooming"]) == ("open", "No")
    assert (trails[2]["StatusEnglish"], trails[2]["Grooming"]) == ("closed", "No")


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="116 trail rows but 0 were read"):
        whitefish.parse(changed("<div class=\"wmr-lift-section\">", "<div class=\"wmr-lift\">"), NOW)
    with pytest.raises(ValueError, match="no name or no status"):
        whitefish.parse(changed("<div class=\"wmr-lift-status-bar\">", "<div class=\"wmr-lift-bar\">", 1), NOW)
    with pytest.raises(ValueError, match="Chair 1 - Big Mountain Express has 0 status pictures"):
        whitefish.parse(changed(LIFT_CLOSED, LIFT_CLOSED.replace("is_closed.svg", "closed.png"), 1), NOW)
    with pytest.raises(ValueError, match="1000 Turns's status picture is closed but reads 'Open'"):
        whitefish.parse(changed(RUN_CLOSED, RUN_CLOSED.replace("alt=\"Closed\"", "alt=\"Open\""), 1), NOW)
    with pytest.raises(ValueError, match="Easy Out has a difficulty drawing the reader does not know: circle and rect"):
        whitefish.parse(changed("<circle fill=\"#393\"", "<circle></circle><rect fill=\"#393\"", 1), NOW)
    # A row that has lost its name runs into the next one, and is refused there.
    with pytest.raises(ValueError, match="Bad Rock has a difficulty drawing the reader does not know: path and rect"):
        whitefish.parse(changed("<div class=\"wmr-col wmr-col-name\">", "<div class=\"wmr-col wmr-name\">", 1), NOW)
    with pytest.raises(ValueError, match="116 trail rows but 115 were read"):
        whitefish.parse(changed("<div class=\"wmr-run-row\"><div class=\"wmr-col\" style=\"width:30px;\">",
                                "<div class=\"wmr-run-row\"><div class=\"wmr-column\">", 1), NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = whitefish.parse(changed("Settled Base", "Deepest Base"), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 14
    assert "SnowReport" not in whitefish.parse(changed("<span class=\"wmr_snow_stat_value\">20\"</span>",
                                                       "<span class=\"wmr_snow_stat_value\">deep</span>"), NOW)
    assert "SnowReport" not in whitefish.parse(changed("wmr_snow_stat_group_header\">Summit",
                                                       "wmr_snow_stat_group_header\">Mid-Mountain"), NOW)
    assert "SnowReport" not in whitefish.parse(changed("wmr_snow_stat_group", "wmr_snow_group"), NOW)
