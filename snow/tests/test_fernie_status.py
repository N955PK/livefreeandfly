from datetime import datetime, timezone
from pathlib import Path

from tahoe_snow.sources import fernie

# The page with its grooming tables and its cookie code taken out; the reader gives the same on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "fernie_refresh.html").read_text()
NOW = datetime(2026, 11, 25, 1, 0, tzinfo=timezone.utc)


def test_the_closed_mountain_reads_its_lifts_and_no_trails():
    # Fernie's page on 2026-11-24, ten days before it opens: 10 lifts, all closed. Its bowl status, which is of
    # zones of terrain and follows the lifts, is not read as lifts.
    feed = fernie.parse(PAGE, NOW)
    assert feed["Name"] == "Fernie" and feed["LastUpdate"] == "2026-11-25T01:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), area["Trails"]) for area in feed["MountainAreas"]] == [("Fernie", 10, [])]
    lifts = feed["MountainAreas"][0]["Lifts"]
    assert [lift["Name"] for lift in lifts] == [
        "Timber Bowl Express Quad", "White Pass Quad", "Polar Peak Chair", "Deer Triple Chair",
        "Great Bear Express Quad", "Elk Quad Chair", "Boomerang Triple Chair", "Haul Back T-Bar",
        "Mighty Moose Platter", "Mini Moose"]
    assert {(lift["Status"], lift["StatusEnglish"], lift["Difficulty"]) for lift in lifts} == {("Closed", "closed", None)}


def test_the_snow_report_is_in_inches_from_the_page_s_centimetres():
    snow = fernie.parse(PAGE, NOW)["SnowReport"]
    # "NOVEMBER 24, 2026 | 7:32am" in Fernie's time, six hours behind UTC.
    assert snow["LastUpdate"] == "2026-11-24T13:32:00Z" and snow["Resortwide"] is True
    # 10 cm of base; 0 cm overnight, 7 cm in 24 and 48 hours, 18 cm in 7 days and 64 cm this season.
    assert snow["BaseArea"] == {"Name": "Bear Weather Plot", "BaseIn": 3.9, "Last24HoursIn": 2.8,
                                "Last48HoursIn": 2.8, "Last7DaysIn": 7.1, "OvernightIn": 0.0}
    assert snow["SeasonTotalIn"] == 25.2 and snow["BaseConditions"] is None
    assert snow["Report"].startswith("Opening Day is almost here!")
