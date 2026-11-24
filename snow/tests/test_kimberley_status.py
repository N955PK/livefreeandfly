from datetime import datetime, timezone
from pathlib import Path

from tahoe_snow.sources import kimberley

# The page with its cookie code taken out; the reader gives the same on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "kimberley_refresh.html").read_text()
NOW = datetime(2026, 11, 25, 1, 0, tzinfo=timezone.utc)


def test_the_closed_mountain_reads_its_lifts_and_no_trails():
    # Kimberley's page on 2026-11-24, before it opens: 5 lifts, all closed. The status of its four faces, which
    # follows the lifts, is not read as lifts.
    feed = kimberley.parse(PAGE, NOW)
    assert feed["Name"] == "Kimberley" and feed["LastUpdate"] == "2026-11-25T01:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), area["Trails"]) for area in feed["MountainAreas"]] == [
        ("Kimberley", 5, [])]
    lifts = feed["MountainAreas"][0]["Lifts"]
    assert [lift["Name"] for lift in lifts] == ["Northstar Express Quad", "Easter", "Tamarack", "Owl T-Bar",
                                                "Owlette Magic Carpet"]
    assert {(lift["Status"], lift["StatusEnglish"], lift["Difficulty"]) for lift in lifts} == {("Closed", "closed", None)}


def test_the_snow_report_is_in_inches_from_the_page_s_centimetres():
    snow = kimberley.parse(PAGE, NOW)["SnowReport"]
    # "NOVEMBER 24, 2026 | 2:14pm" in Kimberley's time, six hours behind UTC.
    assert snow["LastUpdate"] == "2026-11-24T20:14:00Z" and snow["Resortwide"] is True
    # No base yet; 0 cm overnight and in 24 hours, 3 cm in 48 hours, 6 cm in 7 days and 21 cm this season.
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": 0.0, "Last24HoursIn": 0.0, "Last48HoursIn": 1.2,
                                "Last7DaysIn": 2.4, "OvernightIn": 0.0}
    assert snow["SeasonTotalIn"] == 8.3 and snow["BaseConditions"] is None
    assert snow["Report"].startswith("Winter 2026/27")
