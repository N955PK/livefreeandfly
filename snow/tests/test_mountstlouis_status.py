from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import mountstlouis

# The page with its scripts, styles, drawings and comments taken out; the reader gives the same on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "mountstlouis.html").read_text()
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)
CLOSED = '<td style = "text-align: center;" class = "status">Closed</td>'
EASY = '<i class="difficulty easy fas fa-circle" aria-hidden="true"></i><span class="sr-only">Easy</span></td>'
# The first status in the page is the first slope's, by day; the first lift's is found by its name.
LIFT = '<td class = "title">Kinder B</td>\n                                ' + CLOSED


def changed(old: str, new: str, count: int = -1, page: str = PAGE) -> str:
    assert old in page
    return page.replace(old, new, count)


def test_the_preseason_resort_reads_each_hill_s_lifts_and_slopes():
    # Mount St. Louis Moonstone's page on 2026-11-26, before opening: twelve lifts and 37 slopes, all closed.
    feed = mountstlouis.parse(PAGE, NOW)
    assert feed["Name"] == "Mount St. Louis Moonstone" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Mount St. Louis", 7, 18), ("Moonstone", 5, 19)]
    assert [lift["Name"] for lift in feed["MountainAreas"][0]["Lifts"]] == [
        "Kinder B", "Kinder A", "Magic Carpet", "Gentle Ben", "Sundance", "Summit Express", "Josl Huter Express"]
    assert [lift["Name"] for lift in feed["MountainAreas"][1]["Lifts"]] == [
        "Butternut Carpet Lift", "Elfriede Huter Express", "Adventure 8", "Novice Carpet", "Promenade Express"]
    assert feed["MountainAreas"][0]["Lifts"][0] == {"Name": "Kinder B", "Status": "Closed",
                                                    "StatusEnglish": "closed", "Difficulty": None}
    slopes = [slope for area in feed["MountainAreas"] for slope in area["Trails"]]
    assert {slope["StatusEnglish"] for slope in slopes} == {"closed"}
    # No slope carries the snowplough, so nothing is said of grooming.
    assert slopes[0] == {"Name": "Follow Me", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": "Green"}
    levels = [slope["Difficulty"] for slope in slopes]
    assert [levels.count(level) for level in ("Green", "Blue", "Black")] == [13, 15, 9]
    # The base depth is empty before the season, so there is no snow report.
    assert "SnowReport" not in feed


def test_a_base_depth_in_centimetres_is_given_in_inches():
    page = changed("<p><strong>Base Depth: </strong></p>", "<p><strong>Base Depth: </strong>60 cm</p>")
    snow = mountstlouis.parse(page, NOW)["SnowReport"]
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": 23.6, "Last24HoursIn": 0}
    assert snow["LastUpdate"] is None and snow["BaseConditions"] is None and snow["Resortwide"] is True
    page = changed("<p><strong>Base Depth: </strong></p>", "<p><strong>Base Depth: </strong>60-90cm</p>")
    page = changed("</strong>no</p>", "</strong>5 cm</p>", page=page)
    page = changed("<p><strong>Conditions: </strong></p>", "<p><strong>Conditions: </strong>Machine Groomed</p>",
                   page=page)
    snow = mountstlouis.parse(page, NOW)["SnowReport"]
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": None, "BaseMinIn": 23.6, "BaseMaxIn": 35.4,
                                "Last24HoursIn": 2.0}
    assert snow["BaseConditions"] == "Machine Groomed"
    # A snowfall in other words is left out; a depth with no unit, or in other words, costs the snow report.
    page = changed("<p><strong>Base Depth: </strong></p>", "<p><strong>Base Depth: </strong>60 cm</p>")
    snow = mountstlouis.parse(changed("</strong>no</p>", "</strong>Yes</p>", page=page), NOW)["SnowReport"]
    assert snow["BaseArea"]["Last24HoursIn"] is None
    for depth in ("60", "24 inches", "Good"):
        page = changed("<p><strong>Base Depth: </strong></p>", f"<p><strong>Base Depth: </strong>{depth}</p>")
        assert "SnowReport" not in mountstlouis.parse(page, NOW)
    assert "SnowReport" not in mountstlouis.parse(changed("<strong>Base Depth: </strong>", "<strong>Base: </strong>"),
                                                  NOW)


def test_open_slopes_and_lifts_are_read_when_the_page_s_counts_agree():
    page = changed(CLOSED, CLOSED.replace("Closed", "Open"), 2)
    groomed = '<i class="difficulty most-difficult fas fa-light fa-snowplow"></i></td>'
    page = changed(EASY, EASY.replace("</td>", groomed), 1, page)
    page = changed(LIFT, LIFT.replace("Closed", "Open"), 1, page)
    page = changed("0/12 Open Lifts", "1/12 Open Lifts", page=page)
    page = changed("0/37 Open Slopes", "2/37 Open Slopes", page=page)
    area = mountstlouis.parse(page, NOW)["MountainAreas"][0]
    assert area["Lifts"][0] == {"Name": "Kinder B", "Status": "Open", "StatusEnglish": "open", "Difficulty": None}
    assert area["Lifts"][1]["StatusEnglish"] == "closed"
    assert area["Trails"][0] == {"Name": "Follow Me", "Status": "Open", "StatusEnglish": "open", "Difficulty": "Green",
                                 "Grooming": "Yes"}
    assert (area["Trails"][1]["StatusEnglish"], area["Trails"][1]["Grooming"]) == ("open", "No")
    assert (area["Trails"][2]["StatusEnglish"], area["Trails"][2]["Grooming"]) == ("closed", "No")


def test_at_night_the_tables_the_page_s_count_agrees_with_are_read():
    page = changed("0/37 Open Slopes", "1/37 Open Slopes")
    at = page.index('<div id="night-runs"')
    page = page[:at] + page[at:].replace(CLOSED, CLOSED.replace("Closed", "Open"), 1)
    slopes = mountstlouis.parse(page, NOW)["MountainAreas"][0]["Trails"]
    assert [slope["StatusEnglish"] for slope in slopes[:2]] == ["open", "closed"]


def test_another_status_is_carried_in_the_page_s_words_and_a_race_flag_is_passed_over():
    page = changed(CLOSED, CLOSED.replace("Closed", "On Hold"), 1)
    page = changed(EASY, EASY.replace("</td>", '<i class="difficulty most-difficult fas fa-solid fa-flag-checkered">'
                                               "</i></td>"), 1, page)
    slope = mountstlouis.parse(page, NOW)["MountainAreas"][0]["Trails"][0]
    assert slope == {"Name": "Follow Me", "Status": "On hold", "StatusEnglish": "on hold", "Difficulty": "Green"}


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="0 of 37 slopes open but 1 of 37 were read by day and 1 of 37 by night"):
        mountstlouis.parse(PAGE.replace(">Follow Me</td>\n                                " + CLOSED,
                                        ">Follow Me</td>\n                                "
                                        + CLOSED.replace("Closed", "Open")), NOW)
    with pytest.raises(ValueError, match="counts 0 of 12 lifts open but 1 of 12 were read"):
        mountstlouis.parse(changed(LIFT, LIFT.replace("Closed", "Open")), NOW)
    with pytest.raises(ValueError, match="counts 0 of 40 slopes open but 0 of 37 were read"):
        mountstlouis.parse(changed("0/37 Open Slopes", "0/40 Open Slopes"), NOW)
    with pytest.raises(ValueError, match="count of open lifts was not found"):
        mountstlouis.parse(changed("0/12 Open Lifts", "Lifts"), NOW)
    with pytest.raises(ValueError, match="Follow Me has a symbol the reader does not know"):
        mountstlouis.parse(changed(EASY, '<i class="difficulty extreme fas fa-skull"></i></td>', 1), NOW)
    with pytest.raises(ValueError, match="Follow Me has no difficulty symbol"):
        mountstlouis.parse(changed(EASY, "</td>", 1), NOW)
    with pytest.raises(ValueError, match="Follow Me has no name or no status"):
        mountstlouis.parse(changed(CLOSED, CLOSED.replace("Closed", ""), 1), NOW)
    with pytest.raises(ValueError, match="slopes of the day or of the night were not found"):
        mountstlouis.parse(changed('<div id="day-runs"', '<div id="runs"'), NOW)
    with pytest.raises(ValueError, match="not rows of 2 cells"):
        mountstlouis.parse(changed(LIFT, LIFT + "<td>9-4</td>", 1), NOW)
    with pytest.raises(ValueError, match="hills with slopes are not the hills with lifts"):
        mountstlouis.parse(changed("<h4>Moonstone Lifts</h4>", "<h4>North Lifts</h4>"), NOW)
    with pytest.raises(ValueError):
        mountstlouis.parse("<html><body>Not the page</body></html>", NOW)
