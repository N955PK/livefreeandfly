from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import missionridge

PAGE = (Path(__file__).parent / "fixtures" / "missionridge.html").read_text()
NOW = datetime(2026, 11, 23, 23, 40, tzinfo=timezone.utc)


def test_the_closed_mountain_reads_as_every_lift_and_trail_closed_by_chair():
    # Mission Ridge's report on 2026-11-23, before it opened: four chairs, two rope tows and a carpet, all closed.
    feed = missionridge.parse(PAGE, NOW)
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Mission Ridge", 7, 0), ("Chair 1", 0, 6), ("Chair 2", 0, 22), ("Chair 3", 0, 12), ("Chair 4", 0, 8),
        ("Off-Piste Areas", 0, 7), ("Terrain Parks", 0, 2)]
    rows = [row for area in feed["MountainAreas"] for row in area["Lifts"] + area["Trails"]]
    assert {row["StatusEnglish"] for row in rows} == {"closed"} and all(row["Name"] for row in rows)
    assert feed["MountainAreas"][1]["Trails"][0] == {"Name": "Mimi", "Status": "Closed", "StatusEnglish": "closed",
                                                     "Difficulty": "Green"}


def test_open_and_groomed_letters_read_as_open_and_blue_black_as_black():
    page = PAGE.replace('<td class="trail">Mimi</td>\n               <td class="status">X', '<td class="trail">Mimi</td>\n               <td class="status">AM')
    page = page.replace('<td class="trail">Bypass</td>\n               <td class="status">X', '<td class="trail">Bypass</td>\n               <td class="status">O')
    trails = {trail["Name"]: trail for area in missionridge.parse(page, NOW)["MountainAreas"] for trail in area["Trails"]}
    assert trails["Mimi"]["StatusEnglish"] == "open" and trails["Mimi"]["Grooming"] == "Yes"
    assert trails["Bypass"]["StatusEnglish"] == "open" and "Grooming" not in trails["Bypass"]
    assert missionridge.trail_row('<img src="/media/trail-icons/mark-blue-black.svg" />', "Run", "X")["Difficulty"] == "Black"


def test_a_page_whose_trails_do_not_all_read_is_refused():
    with pytest.raises(ValueError, match="trail statuses"):
        missionridge.parse(PAGE.replace('<td class="trail">Mimi</td>', '<td class="name">Mimi</td>', 1), NOW)
    with pytest.raises(ValueError, match="lift table"):
        missionridge.parse(PAGE.replace('<th class="Lift">Lift</th>', ""), NOW)
