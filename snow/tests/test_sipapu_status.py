import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import sipapu

# The page with its scripts, styles, drawings and comments taken out; the reader gives the same on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "sipapu.html").read_text()
NOW = datetime(2026, 11, 26, 14, 0, tzinfo=timezone.utc)


def changed(old: str, new: str, count: int = -1) -> str:
    assert old in PAGE
    return PAGE.replace(old, new, count)


def test_the_early_season_mountain_reads_its_two_open_lifts_and_its_trails():
    # Sipapu's page on 2026-11-26, early season: six lifts with two open, 53 trails with two open.
    feed = sipapu.parse(PAGE, NOW)
    assert feed["Name"] == "Sipapu" and feed["LastUpdate"] == "2026-11-26T14:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Sipapu", 6, 0), ("Trails", 0, 53)]
    assert [(lift["Name"], lift["Status"]) for lift in feed["MountainAreas"][0]["Lifts"]] == [
        ("Lift 1", "Closed"), ("Lift 2", "Open"), ("Lift 3", "Closed"), ("Lift 4", "Closed"), ("Lift 5", "Open"),
        ("Ski School Magic Carpet", "Closed")]
    assert feed["MountainAreas"][0]["Lifts"][1] == {"Name": "Lift 2", "Status": "Open", "StatusEnglish": "open",
                                                    "Difficulty": None}
    trails = feed["MountainAreas"][1]["Trails"]
    assert len({trail["Name"] for trail in trails}) == 53
    assert trails[0] == {"Name": "Badger’s Trail", "Status": "Closed", "StatusEnglish": "closed",
                         "Difficulty": "Green", "Grooming": "No"}
    opened = [trail for trail in trails if trail["StatusEnglish"] == "open"]
    assert len(opened) == 2 and opened[0] == {"Name": "Lower Bambi", "Status": "Open", "StatusEnglish": "open",
                                              "Difficulty": "Green", "Grooming": "Yes"}
    assert {trail["Difficulty"] for trail in trails} == {"Green", "Blue", "Black", "Double black"}


def test_the_snow_figures_are_read_and_undated():
    snow = sipapu.parse(PAGE, NOW)["SnowReport"]
    # The page does not say when its figures were written.
    assert snow["LastUpdate"] is None and snow["Resortwide"] is True and snow["BaseConditions"] is None
    assert snow["BaseArea"] == {"Name": "Mountain", "Last24HoursIn": 0, "Last48HoursIn": 0, "Last72HoursIn": 1,
                                "Last7DaysIn": 7, "BaseIn": 14}
    assert snow["SeasonTotalIn"] == 15


def test_a_lift_s_other_status_is_carried_in_the_page_s_words():
    page = changed('<li class="m-lift-status-closed">', '<li class="m-lift-status-on-hold">', 1)
    page = page.replace('m-status m-margin-bottom m-status-closed">Closed<',
                        'm-status m-margin-bottom m-status-on-hold">On Hold<', 1)
    lift = sipapu.parse(page, NOW)["MountainAreas"][0]["Lifts"][0]
    assert (lift["Name"], lift["Status"], lift["StatusEnglish"]) == ("Lift 1", "On hold", "on hold")


def test_an_all_closed_mountain_reads_as_closed():
    page = (PAGE.replace("m-lift-status-open", "m-lift-status-closed").replace("m-status-open", "m-status-closed")
            .replace("m-filter-value-open", "m-filter-value-closed"))
    page = re.sub(r"Open(\s*</div>)", r"Closed\1", page)
    feed = sipapu.parse(page, NOW)
    rows = [row for area in feed["MountainAreas"] for row in area["Lifts"] + area["Trails"]]
    assert len(rows) == 59 and {row["StatusEnglish"] for row in rows} == {"closed"}


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="list of lifts was not found"):
        sipapu.parse(changed('<ul class="m-lifts-list', '<ul class="m-chairs-list'), NOW)
    with pytest.raises(ValueError, match="Lift 1 is marked closed but reads 'Shut'"):
        sipapu.parse(changed('m-status m-margin-bottom m-status-closed">Closed<',
                             'm-status m-margin-bottom m-status-closed">Shut<', 1), NOW)
    with pytest.raises(ValueError, match="7 lift rows but 6 were read"):
        sipapu.parse(changed("<main ", "<li class=\"m-lift-status-closed\"></li><main "), NOW)
    with pytest.raises(ValueError, match="54 trail rows but 53 were read"):
        sipapu.parse(changed("<main ", "<li class=\"m-filter-target\"></li><main "), NOW)
    with pytest.raises(ValueError, match="list of trails was not found"):
        sipapu.parse(changed('m-lifts-and-trails">', 'm-trails">'), NOW)
    with pytest.raises(ValueError, match="difficulty the reader does not know: orange"):
        sipapu.parse(changed("m-status-green\">Bambi<", "m-status-orange\">Bambi<"), NOW)
    with pytest.raises(ValueError, match="no grooming the reader knows"):
        sipapu.parse(changed("m-filter-value-not-groomed", "m-filter-value-corduroy", 1), NOW)
    with pytest.raises(ValueError, match="lists no trails"):
        sipapu.parse(changed('<li class="m-accordion">', '<li class="m-group">'), NOW)
    with pytest.raises(ValueError, match="lists no lifts"):
        sipapu.parse(changed('<li class="m-lift-status-', '<li class="m-chair-status-'), NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = sipapu.parse(changed("14&#8243;", "deep"), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 2
    assert "SnowReport" not in sipapu.parse(changed("Base Depth        </div>", "Summit Depth        </div>", 1), NOW)
    assert "SnowReport" not in sipapu.parse(changed("m-snow-totals-table-header", "m-snow-table-header"), NOW)
