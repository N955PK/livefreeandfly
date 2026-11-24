from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import montsainteanne

FIXTURES = Path(__file__).parent / "fixtures"
# The frame the conditions page loads, whole.
PAGE = (FIXTURES / "montsainteanne.html").read_text()
MIDSEASON = (FIXTURES / "montsainteanne_midseason.html").read_text()
NOW = datetime(2026, 11, 24, 18, 0, tzinfo=timezone.utc)


def changed(old: str, new: str, page: str = PAGE) -> str:
    assert old in page
    return page.replace(old, new)


def rows(feed: dict, kind: str) -> list:
    return [row for area in feed["MountainAreas"] for row in area[kind]]


def test_the_closed_mountain_reads_its_lifts_and_its_trails_by_side():
    # Mont-Sainte-Anne's frame on 2026-11-24, before the season: nine lifts and 71 trails, all closed.
    feed = montsainteanne.parse(PAGE, NOW)
    assert feed["Name"] == "Mont-Sainte-Anne" and feed["LastUpdate"] == "2026-11-24T18:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Mont-Sainte-Anne", 9, 0), ("South Side", 0, 50), ("North Side", 0, 16), ("West Side", 0, 5)]
    assert [lift["Name"] for lift in rows(feed, "Lifts")] == [
        "Panorama Express", "L'Étoile Filante", "L'Express du Sud", "La Tortue", "Le Mille-Pattes",
        "La Montée Magique", "L'Express du Nord", "L'Échappée", "La Corde Raide"]
    assert rows(feed, "Lifts")[0] == {"Name": "Panorama Express", "Status": "Closed", "StatusEnglish": "closed",
                                      "Difficulty": None}
    assert {row["StatusEnglish"] for row in rows(feed, "Lifts") + rows(feed, "Trails")} == {"closed"}
    # Schnell's name is followed by a glade's tree, which is not part of it.
    assert rows(feed, "Trails")[:2] == [
        {"Name": "La Crête", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": "Black", "Grooming": "No"},
        {"Name": "Schnell", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": "Black", "Grooming": "No"}]
    assert {trail["Difficulty"] for trail in rows(feed, "Trails")} == {"Green", "Blue", "Black", "Double black"}


def test_the_midseason_mountain_reads_ouvert_as_open_and_the_grooming_marks():
    # The frame as the Internet Archive kept it on 2026-02-04: five of nine lifts turning, 60 of 71 trails open.
    feed = montsainteanne.parse(MIDSEASON, NOW)
    assert [(lift["Name"], lift["StatusEnglish"]) for lift in rows(feed, "Lifts")] == [
        ("Panorama Express", "open"), ("L'Étoile Filante", "open"), ("L'Express du Sud", "open"),
        ("La Tortue", "closed"), ("Le Mille-Pattes", "open"), ("La Montée Magique", "closed"),
        ("L'Express du Nord", "open"), ("L'Échappée", "closed"), ("La Corde Raide", "closed")]
    trails = rows(feed, "Trails")
    assert len(trails) == 71 and sum(trail["StatusEnglish"] == "open" for trail in trails) == 60
    assert sum(trail["Grooming"] == "Yes" for trail in trails) == 21
    assert trails[0] == {"Name": "La Crête", "Status": "Open", "StatusEnglish": "open", "Difficulty": "Black",
                         "Grooming": "Yes"}


def test_the_snowfall_is_turned_from_centimetres_into_inches_and_there_is_no_depth():
    snow = montsainteanne.parse(MIDSEASON, NOW)["SnowReport"]
    # "2026-02-04 6:12 am", five hours behind UTC in February; a season of 296 cm.
    assert snow["LastUpdate"] == "2026-02-04T11:12:00Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Mountain", "Last24HoursIn": 0.0, "Last48HoursIn": 0.0, "Last7DaysIn": 0.0}
    assert snow["SeasonTotalIn"] == 116.5 and snow["BaseConditions"] is None
    assert montsainteanne.parse(PAGE, NOW)["SnowReport"]["LastUpdate"] == "2026-11-11T14:38:00Z"
    feed = montsainteanne.parse(changed('24h</div><div class="snowreport-snowfall-box-value-element">0<',
                                        '24h</div><div class="snowreport-snowfall-box-value-element">12<'), NOW)
    assert feed["SnowReport"]["BaseArea"]["Last24HoursIn"] == 4.7


def test_a_frame_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="status mark the reader does not know"):
        montsainteanne.parse(changed('<span class="largeminus">&nbsp;</span>', '<span class="largewait"></span>'), NOW)
    with pytest.raises(ValueError, match="status titles"):
        montsainteanne.parse(changed('title="FERM&Eacute;"', 'title="EN ATTENTE"'), NOW)
    with pytest.raises(ValueError, match="difficulty pictures"):
        montsainteanne.parse(changed("conditions/D_diamond.svg", "conditions/hardest.svg"), NOW)
    with pytest.raises(ValueError, match="counts 10 lifts but 9"):
        montsainteanne.parse(changed('<div class="snowreport-column-value">0 / 9</div>',
                                     '<div class="snowreport-column-value">0 / 10</div>'), NOW)
    with pytest.raises(ValueError, match="counts 72 trails but 71"):
        montsainteanne.parse(changed('<div class="snowreport-column-value">0 / 71</div>',
                                     '<div class="snowreport-column-value">0 / 72</div>'), NOW)
    with pytest.raises(ValueError, match="counts 4 lifts open"):
        montsainteanne.parse(changed('<div class="snowreport-column-value">5 / 9</div>',
                                     '<div class="snowreport-column-value">4 / 9</div>', MIDSEASON), NOW)
    with pytest.raises(ValueError, match="does not fill trails-west-day-element-msa"):
        montsainteanne.parse(changed("getElementById('trails-west-day-element-msa')",
                                     "getElementById('trails-west-day')"), NOW)
    with pytest.raises(ValueError, match="fills no element"):
        montsainteanne.parse("<html><body>One moment, please...</body></html>", NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = montsainteanne.parse(changed("2026-11-11 9:38 am", "this morning"), NOW)
    assert "SnowReport" not in feed and len(rows(feed, "Lifts")) == 9
    assert "SnowReport" not in montsainteanne.parse(changed(
        '<div class="snowreport-snowfall-box-title-element">24h</div>',
        '<div class="snowreport-snowfall-box-title-element">Today</div>'), NOW)
