from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import sutton

# The page with its scripts, styles and drawings taken out; the reader gives the same on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "sutton.html").read_text()
NOW = datetime(2026, 11, 25, 0, 0, tzinfo=timezone.utc)
CLOSED_LIFT = '<div class="flexible_statuts_list_cell">Closed</div>'
CLOSED_TRAIL = '<div class="flexible_liste_des_pistes_list_cell -status -closed">Closed</div>'


def changed(old: str, new: str, count: int = -1) -> str:
    assert old in PAGE
    return PAGE.replace(old, new, count)


def test_the_closed_mountain_reads_its_chairlifts_and_trails():
    # Mont Sutton's page on 2026-11-24, before the season: seven chairlifts and the magic carpets, all closed.
    feed = sutton.parse(PAGE, NOW)
    assert feed["Name"] == "Mont Sutton" and feed["LastUpdate"] == "2026-11-25T00:00:00Z"
    assert [area["Name"] for area in feed["MountainAreas"]] == ["Mont Sutton"]
    lifts, trails = feed["MountainAreas"][0]["Lifts"], feed["MountainAreas"][0]["Trails"]
    assert [lift["Name"] for lift in lifts] == [
        "Chairlift I", "Chairlift II", "Chairlift III", "Chairlift IV", "Chairlift IV Ouest", "Chairlift V",
        "Chairlift VII", "Tapis magiques"]
    assert lifts[1] == {"Name": "Chairlift II", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}
    assert {row["StatusEnglish"] for row in lifts + trails} == {"closed"}
    # The page counts 60 trails; it lists 66, some of them the top and the bottom of one trail, and shows the list twice.
    assert len(trails) == 66
    assert trails[0] == {"Name": "Alleghanys (haut/top)", "Status": "Closed", "StatusEnglish": "closed",
                         "Difficulty": "Blue", "Grooming": "No"}
    # Coucou is marked easy and difficult: it is given the harder.
    assert trails[1]["Name"] == "Coucou" and trails[1]["Difficulty"] == "Blue"
    assert {trail["Difficulty"] for trail in trails} == {"Green", "Blue", "Black", "Double black"}


def test_the_snow_report_is_in_inches_and_dated():
    snow = sutton.parse(PAGE, NOW)["SnowReport"]
    # "21 November 2026 – 10H 57 MIN", five hours behind UTC in November.
    assert snow["LastUpdate"] == "2026-11-21T15:57:00Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": None, "Last24HoursIn": 0, "Last48HoursIn": 0,
                                "Last7DaysIn": 0}
    assert snow["SeasonTotalIn"] == 0 and snow["BaseConditions"] is None
    day = ('<span class="flexible_conditions_list_snow_item_label">24 H</span>\n'
           '\t\t\t\t\t\t<span class="flexible_conditions_list_snow_item_value">0 <span')
    snow = sutton.parse(changed(day, day.replace(">0 <span", ">12 <span")), NOW)["SnowReport"]
    # 12 cm.
    assert snow["BaseArea"]["Last24HoursIn"] == 4.7 and snow["BaseArea"]["Last48HoursIn"] == 0


def test_an_open_lift_and_an_open_groomed_trail_read_as_open():
    page = changed(CLOSED_LIFT, CLOSED_LIFT.replace("Closed", "Open"), 2)
    page = page.replace(CLOSED_TRAIL + "\n\t\t\t\t" + '<div class="flexible_liste_des_pistes_list_cell">Ungroomed</div>',
                        CLOSED_TRAIL.replace("Closed", "Open") + "\n\t\t\t\t"
                        + '<div class="flexible_liste_des_pistes_list_cell">Groomed</div>', 1)
    assert page.count(">Groomed<") == 1
    area = sutton.parse(page, NOW)["MountainAreas"][0]
    assert [lift["StatusEnglish"] for lift in area["Lifts"]][:3] == ["open", "open", "closed"]
    assert area["Trails"][0]["StatusEnglish"] == "open" and area["Trails"][0]["Grooming"] == "Yes"
    # The drawer's copy of the first trail still says closed, so the two are different rows.
    assert len(area["Trails"]) == 67
    hold = sutton.parse(changed(CLOSED_LIFT, CLOSED_LIFT.replace("Closed", "En attente"), 1), NOW)
    assert hold["MountainAreas"][0]["Lifts"][0]["Status"] == "On hold"


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="not one the reader knows"):
        sutton.parse(changed(CLOSED_LIFT, CLOSED_LIFT.replace("Closed", "Wind"), 1), NOW)
    with pytest.raises(ValueError, match="difficulty pictures"):
        sutton.parse(changed("type_piste_extreme.svg", "type_piste_expert.svg"), NOW)
    with pytest.raises(ValueError, match="table of chairlifts was not found"):
        sutton.parse(changed("flexible_statuts -telesieges", "flexible_statuts -lifts"), NOW)
    with pytest.raises(ValueError, match="counts 9 chairlifts but 7"):
        sutton.parse(changed(">0/7<", ">0/9<"), NOW)
    with pytest.raises(ValueError, match="counts 90 trails but only 66"):
        sutton.parse(changed(">0/60<", ">0/90<"), NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = sutton.parse(changed("10H 57 MIN", "this morning"), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"][0]["Lifts"]) == 8
    assert "SnowReport" not in sutton.parse(changed("snow_item_label\">24 H<", "snow_item_label\">Overnight<"), NOW)
