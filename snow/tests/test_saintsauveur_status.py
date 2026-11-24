from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import saintsauveur

# The page with its scripts, styles, drawings, pictures and menus taken out; the reader gives the same on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "saintsauveur.html").read_text()
NOW = datetime(2026, 11, 25, 0, 0, tzinfo=timezone.utc)
# Sommet Express, in the page's JSON as its attributes hold it.
EXPRESS = ("&quot;IsDay&quot;:true,&quot;IsDayOpen&quot;:false,&quot;IsNight&quot;:true,&quot;IsNightOpen&quot;:false,"
           "&quot;Name&quot;:&quot;Sommet Express&quot;")


def changed(old: str, new: str, count: int = -1) -> str:
    assert old in PAGE
    return PAGE.replace(old, new, count)


def test_the_closed_mountain_reads_saint_sauveur_and_avila():
    # Les Sommets' page on 2026-11-24, before the season: six mountains, of which these two are read.
    feed = saintsauveur.parse(PAGE, NOW)
    assert feed["Name"] == "Sommet Saint-Sauveur" and feed["LastUpdate"] == "2026-11-25T00:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Sommet Saint-Sauveur", 9, 41), ("Versant Avila", 4, 14)]
    lifts = [lift for area in feed["MountainAreas"] for lift in area["Lifts"]]
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    assert len(lifts) == 13
    assert lifts[0] == {"Name": "Flèche d'Argent", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}
    assert {"Sommet Express", "L'Étoile", "Avila Express"} <= {lift["Name"] for lift in lifts}
    assert {row["StatusEnglish"] for row in lifts + trails} == {"closed"}
    assert trails[0] == {"Name": "Nordique", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": "Black",
                         "Grooming": "Yes"}
    assert {trail["Difficulty"] for trail in trails} == {"Green", "Blue", "Black", "Double black", ""}


def test_the_snow_report_is_in_inches_and_dated():
    snow = saintsauveur.parse(PAGE, NOW)["SnowReport"]
    # "Information updated November 24 2026 at 15h41", five hours behind UTC in November.
    assert snow["LastUpdate"] == "2026-11-24T20:41:00Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": None, "Last24HoursIn": 0, "Last48HoursIn": 0}
    assert snow["SeasonTotalIn"] == 0 and snow["BaseConditions"] == "Machine Groomed"
    # The first figure on the page is Saint-Sauveur's last 24 hours: 8 cm.
    snow = saintsauveur.parse(changed(">0 cm</div>", ">8 cm</div>", 1), NOW)["SnowReport"]
    assert snow["BaseArea"]["Last24HoursIn"] == 3.1 and snow["BaseArea"]["Last48HoursIn"] == 0


def test_a_lift_is_open_by_the_half_of_the_day_the_page_is_showing():
    # The page was saved in the evening, showing the night: open by night is open, open only by day is not.
    by_night = saintsauveur.parse(changed(EXPRESS, EXPRESS.replace("IsNightOpen&quot;:false", "IsNightOpen&quot;:true")),
                                  NOW)
    assert [lift["StatusEnglish"] for lift in by_night["MountainAreas"][0]["Lifts"][:3]] == ["closed", "open", "closed"]
    by_day = changed(EXPRESS, EXPRESS.replace("IsDayOpen&quot;:false", "IsDayOpen&quot;:true"))
    assert {lift["StatusEnglish"] for lift in saintsauveur.parse(by_day, NOW)["MountainAreas"][0]["Lifts"]} == {"closed"}
    # The same page showing the day.
    shown_by_day = by_day.replace('data-is-night-prop="True"', 'data-is-night-prop="False"')
    lifts = saintsauveur.parse(shown_by_day, NOW)["MountainAreas"][0]["Lifts"]
    assert [lift["Name"] for lift in lifts if lift["StatusEnglish"] == "open"] == ["Sommet Express"]


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="twice, differently"):
        saintsauveur.parse(changed(EXPRESS, EXPRESS.replace("IsNightOpen&quot;:false", "IsNightOpen&quot;:true"), 1),
                           NOW)
    with pytest.raises(ValueError, match="does not say whether it is open"):
        saintsauveur.parse(changed(EXPRESS, EXPRESS.replace("IsNightOpen", "OpenAtNight")), NOW)
    with pytest.raises(ValueError, match="not one the reader knows"):
        saintsauveur.parse(changed("&quot;Difficulty&quot;:&quot;Extreme&quot;",
                                   "&quot;Difficulty&quot;:&quot;Expert&quot;"), NOW)
    with pytest.raises(ValueError, match="counts 10 lifts at Sommet Saint-Sauveur but 9"):
        saintsauveur.parse(changed("&quot;LiftDayOpen&quot;:&quot;0 / 9&quot;", "&quot;LiftDayOpen&quot;:&quot;0 / 10&quot;"),
                           NOW)
    with pytest.raises(ValueError, match="no block for \\['Versant Avila'\\]"):
        saintsauveur.parse(changed("&quot;Name&quot;:&quot;Versant Avila&quot;", "&quot;Name&quot;:&quot;Avila&quot;"), NOW)
    with pytest.raises(ValueError, match="no block for"):
        saintsauveur.parse(changed("sommets-app-conditions-winter-list", "sommets-app-conditions-list"), NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = saintsauveur.parse(changed("Information updated", "Updated"), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 2
    assert "SnowReport" not in saintsauveur.parse(changed("Last 24 hours", "Overnight"), NOW)
