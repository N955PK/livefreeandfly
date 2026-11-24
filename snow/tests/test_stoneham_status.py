from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import stoneham

# The frame the conditions page loads, whole.
PAGE = (Path(__file__).parent / "fixtures" / "stoneham.html").read_text()
NOW = datetime(2026, 11, 24, 18, 0, tzinfo=timezone.utc)


def changed(old: str, new: str) -> str:
    assert old in PAGE
    return PAGE.replace(old, new)


def test_the_closed_mountain_reads_its_lifts_and_trails():
    # Stoneham's frame on 2026-11-24, before the season: six lifts and 43 trails, all closed.
    feed = stoneham.parse(PAGE, NOW)
    assert feed["Name"] == "Stoneham" and feed["LastUpdate"] == "2026-11-24T18:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Stoneham", 6, 0), ("Trails", 0, 43)]
    lifts, trails = feed["MountainAreas"][0]["Lifts"], feed["MountainAreas"][1]["Trails"]
    assert [lift["Name"] for lift in lifts] == ["A - L'Alizé", "B - Le Tapis Magique", "C - Le Mille-Pattes",
                                               "H - La Tempête", "I - L'Aurore Boréale", "E - Éclipse"]
    assert lifts[0] == {"Name": "A - L'Alizé", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}
    assert {row["StatusEnglish"] for row in lifts + trails} == {"closed"}
    assert trails[0] == {"Name": "1- Walter Moisan", "Status": "Closed", "StatusEnglish": "closed",
                         "Difficulty": "Black", "Grooming": "No"}
    # L'Urubu's name is followed by a glade's tree, which is not part of it.
    assert trails[3]["Name"] == "1C- L'Urubu"
    assert {trail["Difficulty"] for trail in trails} == {"Green", "Blue", "Black", "Double black"}


def test_an_open_mountain_reads_the_tick_and_ouvert_as_open():
    page = changed('<div class="lift-open"><span class="largeminus">&nbsp;</span></div>',
                   '<div class="lift-open"><i class="icons icon-check largecheck"></i></div>')
    page = page.replace('title="FERM&Eacute;"', 'title="OUVERT"').replace(
        '<div class="snowreport-column-value">0 / 6</div>', '<div class="snowreport-column-value">6 / 6</div>')
    feed = stoneham.parse(page, NOW)
    rows = [row for area in feed["MountainAreas"] for row in area["Lifts"] + area["Trails"]]
    assert len(rows) == 49 and {row["StatusEnglish"] for row in rows} == {"open"}


def test_the_snowfall_is_turned_from_centimetres_into_inches_and_there_is_no_depth():
    snow = stoneham.parse(PAGE, NOW)["SnowReport"]
    # "2026-04-07 06h51 am", four hours behind UTC in April: last season's report, which the runner leaves out as
    # old. 13 cm in 7 days and a season of 365 cm.
    assert snow["LastUpdate"] == "2026-04-07T10:51:00Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Mountain", "Last24HoursIn": 0.0, "Last48HoursIn": 0.0, "Last7DaysIn": 5.1}
    assert snow["SeasonTotalIn"] == 143.7 and snow["BaseConditions"] is None


def test_a_frame_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="status mark the reader does not know"):
        stoneham.parse(changed('<span class="largeminus">&nbsp;</span>', '<span class="largewait"></span>'), NOW)
    with pytest.raises(ValueError, match="counts 7 lifts but 6"):
        stoneham.parse(changed('<div class="snowreport-column-value">0 / 6</div>',
                               '<div class="snowreport-column-value">0 / 7</div>'), NOW)
    with pytest.raises(ValueError, match="counts 44 trails but 43"):
        stoneham.parse(changed('Trails open</div><div class="snowreport-column-value">0 / 43</div>',
                               'Trails open</div><div class="snowreport-column-value">0 / 44</div>'), NOW)
    # The site has answered some readers with a check page instead of the frame.
    with pytest.raises(ValueError, match="fills no element"):
        stoneham.parse("<html><head><title>One moment, please...</title></head></html>", NOW)
