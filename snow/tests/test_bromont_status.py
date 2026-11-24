from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import bromont

# The page with its scripts, styles, drawings and banner comments taken out; the reader gives the same on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "bromont.html").read_text()
NOW = datetime(2026, 11, 25, 0, 0, tzinfo=timezone.utc)
DIRECTE = ('<div class="statut strm_3"><span class="statut_titre_mobile"> In real time</span> <i></i> Closed </div>', 1)


def changed(old: str, new: str, count: int = -1) -> str:
    assert old in PAGE
    return PAGE.replace(old, new, count)


def test_the_closed_mountain_reads_each_side_with_its_lifts_and_trails():
    # Bromont's page on 2026-11-24, before the season: eleven lifts, 96 trails and 29 glades, all closed.
    feed = bromont.parse(PAGE, NOW)
    assert feed["Name"] == "Bromont" and feed["LastUpdate"] == "2026-11-25T00:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Versant du Village", 2, 32), ("Versant du Lac", 1, 24), ("Versant des Épinettes", 1, 15),
        ("Mont soleil", 4, 8), ("Versant des Cantons", 1, 19), ("Versant du Midi", 1, 9),
        ("Versant de la Côte Ouest", 1, 18)]
    lifts = [lift for area in feed["MountainAreas"] for lift in area["Lifts"]]
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    assert len(lifts) == 11 and len(trails) == 125
    assert lifts[0] == {"Name": "#3 Télésiège quadruple - La Directe", "Status": "Closed", "StatusEnglish": "closed",
                        "Difficulty": None}
    assert lifts[1]["Name"] == "#4 Télésiège sextuple et télécabines - L'Express du Village"
    assert {row["StatusEnglish"] for row in lifts + trails} == {"closed"}
    assert trails[0] == {"Name": "Brome", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": "Green"}
    assert {trail["Difficulty"] for trail in trails} == {"Green", "Blue", "Black", "Double black"}
    # A glade has a second symbol beside its difficulty, and only a dash for the evening.
    village = feed["MountainAreas"][0]["Trails"]
    assert village[27] == {"Name": "St-Lambert", "Status": "Closed", "StatusEnglish": "closed",
                           "Difficulty": "Double black"}


def test_the_snow_report_is_in_inches_and_dated():
    snow = bromont.parse(PAGE, NOW)["SnowReport"]
    # "Updated on 24-11-2026 18:12:01", five hours behind UTC in November.
    assert snow["LastUpdate"] == "2026-11-24T23:12:01Z" and snow["Resortwide"] is True
    # The page gives no base depth, and "--" for its surface before the season.
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": None, "Last24HoursIn": 0, "Last48HoursIn": 0,
                                "Last7DaysIn": 0}
    assert snow["BaseConditions"] is None
    # 392 cm, last season's total still on the page.
    assert snow["SeasonTotalIn"] == 154.3
    surface = "Surface</span>\n" + "\t" * 8 + "<p>\n" + "\t" * 9 + "--"
    assert surface in PAGE
    page = changed("0 cm\n", "13 cm\n").replace(surface, surface.replace("--", "Packed powder"))
    snow = bromont.parse(page, NOW)["SnowReport"]
    assert snow["BaseArea"]["Last24HoursIn"] == 5.1 and snow["BaseConditions"] == "Packed powder"


def test_a_lift_s_real_time_word_and_a_trail_s_day_word_are_their_statuses():
    feed = bromont.parse(changed(DIRECTE[0], DIRECTE[0].replace("Closed", "Open"), 1), NOW)
    assert feed["MountainAreas"][0]["Lifts"][0]["StatusEnglish"] == "open"
    assert feed["MountainAreas"][0]["Lifts"][1]["StatusEnglish"] == "closed"
    feed = bromont.parse(changed(DIRECTE[0], DIRECTE[0].replace("Closed", "On hold"), 1), NOW)
    assert feed["MountainAreas"][0]["Lifts"][0]["Status"] == "On hold"
    # The French words, should the page fall back to them.
    feed = bromont.parse(changed(DIRECTE[0], DIRECTE[0].replace("Closed", "En attente"), 1), NOW)
    assert feed["MountainAreas"][0]["Lifts"][0]["StatusEnglish"] == "on hold"
    brome = ('<span class="nom">Brome</span>\n          <span class="jour">\n        <i class="ico-jour"></i>\n'
             '        Closed')
    feed = bromont.parse(changed(brome, brome.replace("Closed", "Open")), NOW)
    assert [trail["StatusEnglish"] for trail in feed["MountainAreas"][0]["Trails"][:2]] == ["open", "closed"]


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="not one the reader knows"):
        bromont.parse(changed(DIRECTE[0], DIRECTE[0].replace("Closed", "Wind"), 1), NOW)
    with pytest.raises(ValueError, match="difficulty symbols"):
        bromont.parse(changed("ico-tdifficile", "ico-extreme"), NOW)
    with pytest.raises(ValueError, match="counts 11 lifts but 10"):
        bromont.parse(changed('<div class="liste remonte grid-4">', '<div class="rangee remonte grid-4">', 1), NOW)
    with pytest.raises(ValueError, match="counts 11 lifts but 107"):
        bromont.parse(changed('id="recap-pistes"', 'id="pistes"'), NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = bromont.parse(changed("Updated on", "Mis à jour"), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 7
    assert "SnowReport" not in bromont.parse(changed("Last 24 hrs", "Overnight"), NOW)
