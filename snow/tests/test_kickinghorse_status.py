from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import kickinghorse

# The page with its analytics script, its grooming tables and its cookie code taken out; the reader gives the same
# on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "kickinghorse_refresh.html").read_text()
NOW = datetime(2026, 11, 25, 1, 0, tzinfo=timezone.utc)
CLOSED = "<span style='font-weight:bold;font-family:montserrat;'>CLOSED</span>"


def page(old: str, new: str, count: int = -1) -> str:
    assert old in PAGE
    return PAGE.replace(old, new, count)


def test_the_closed_mountain_reads_its_lifts_and_no_trails():
    # Kicking Horse's page on 2026-11-24, before it opens: 5 lifts, all closed. The page gives no status for a run.
    feed = kickinghorse.parse(PAGE, NOW)
    assert feed["Name"] == "Kicking Horse" and feed["LastUpdate"] == "2026-11-25T01:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), area["Trails"]) for area in feed["MountainAreas"]] == [
        ("Kicking Horse", 5, [])]
    lifts = feed["MountainAreas"][0]["Lifts"]
    # The page writes the names in capitals: "GOLDEN EAGLE EXPRESS".
    assert [lift["Name"] for lift in lifts] == ["Golden Eagle Express", "Stairway To Heaven", "Pioneer", "Catamount",
                                                "Jelly Bean Surface Lift"]
    assert lifts[0] == {"Name": "Golden Eagle Express", "Status": "Closed", "StatusEnglish": "closed",
                        "Difficulty": None}
    assert {lift["StatusEnglish"] for lift in lifts} == {"closed"}


def test_the_snow_report_is_in_inches_from_the_page_s_centimetres():
    snow = kickinghorse.parse(PAGE, NOW)["SnowReport"]
    # "NOVEMBER 24, 2026 | 4:41am" in Golden's time, six hours behind UTC.
    assert snow["LastUpdate"] == "2026-11-24T10:41:00Z" and snow["Resortwide"] is True
    # 31 cm of base; 0 cm overnight and in 24 hours, 1 cm in 48 hours, 2 cm in 7 days and 58 cm this season.
    assert snow["BaseArea"] == {"Name": "Alpine Snow Plot", "BaseIn": 12.2, "Last24HoursIn": 0.0,
                                "Last48HoursIn": 0.4, "Last7DaysIn": 0.8, "OvernightIn": 0.0}
    assert snow["SeasonTotalIn"] == 22.8 and snow["BaseConditions"] is None and snow["Alert"] is None
    assert snow["Report"].startswith("Cold temps, busy snowguns") and "<" not in snow["Report"]
    said = kickinghorse.parse(page("<span class='rcr-element-box-conditions-subtitle'>UPPER MTN</span>",
                                   "<span class='rcr-element-box-conditions-subtitle'>UPPER MTN</span> Packed Powder"),
                              NOW)["SnowReport"]
    assert said["BaseConditions"] == "Packed Powder"
    afternoon = kickinghorse.parse(page("NOVEMBER 24, 2026 | 4:41am", "JANUARY 5, 2027 | 12:05pm"), NOW)["SnowReport"]
    assert afternoon["LastUpdate"] == "2027-01-05T18:05:00Z"


def test_open_and_held_lifts_are_read():
    opened = page(CLOSED, "<span style='font-weight:bold;font-family:montserrat;'>OPEN</span>", 2)
    held = opened.replace(CLOSED, "<span style='font-weight:bold;font-family:montserrat;'>ON HOLD</span>", 1)
    lifts = kickinghorse.parse(held, NOW)["MountainAreas"][0]["Lifts"]
    assert [(lift["Name"], lift["Status"], lift["StatusEnglish"]) for lift in lifts] == [
        ("Golden Eagle Express", "Open", "open"), ("Stairway To Heaven", "Open", "open"),
        ("Pioneer", "On hold", "on hold"), ("Catamount", "Closed", "closed"),
        ("Jelly Bean Surface Lift", "Closed", "closed")]


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="PIONEER has a status the reader does not know: 'wind hold'"):
        kickinghorse.parse(page("PIONEER: " + CLOSED, "PIONEER: " + CLOSED.replace("CLOSED", "WIND HOLD")), NOW)
    with pytest.raises(ValueError, match="snowReportPioneerStatus does not read as a lift and its status"):
        kickinghorse.parse(page("PIONEER: " + CLOSED, "PIONEER CLOSED"), NOW)
    with pytest.raises(ValueError, match="lift status was not found"):
        kickinghorse.parse(page("snowReportTH_SnowreportLiftsSaveDate", "snowReportLiftsSaved"), NOW)
    with pytest.raises(ValueError, match="lists no lifts"):
        kickinghorse.parse(PAGE[:PAGE.index("if (parent.document.getElementById('snowReportGoldenEagleExpressStatus'")]
                           + PAGE[PAGE.index("if (parent.document.getElementById('snowReportTH_SnowreportBowlsSave"):],
                           NOW)
    with pytest.raises(ValueError, match="lists a lift twice"):
        kickinghorse.parse(page("PIONEER: ", "CATAMOUNT: "), NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    for old, new in (("snowReportNewSnowFallPack').innerHTML= \"31 \"", "snowReportNewSnowFallPack').innerHTML= \"\""),
                     ("NOVEMBER 24, 2026 | 4:41am \";}\nif (parent.document.getElementById('snowReportNewSnowFallOver",
                      "TODAY \";}\nif (parent.document.getElementById('snowReportNewSnowFallOver"),
                     ("snowReportNewSnowFallYTD", "snowReportSeason"),
                     ("snowReportNewSnowFall24').innerHTML= \"0 \"", "snowReportNewSnowFall24').innerHTML= \"trace \"")):
        feed = kickinghorse.parse(page(old, new), NOW)
        assert "SnowReport" not in feed and len(feed["MountainAreas"][0]["Lifts"]) == 5
