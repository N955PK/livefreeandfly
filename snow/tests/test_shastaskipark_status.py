import csv
import io
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import shastaskipark

# The ski park's published sheet on 2026-11-24, before its season: its headings and no report.
SHEET = (Path(__file__).parent / "fixtures" / "shastaskipark.csv").read_text()
NOW = datetime(2026, 11, 24, 18, 0, tzinfo=timezone.utc)
# A report made up for these tests in the sheet's own columns: the real sheet had none to save, so the words a
# real report uses ("Open", "Closed") are taken from the page's script and are not yet seen.
REPORT = {"Timestamp": "12/19/2026 15:42:10", "Operating Hours": "9am - 4pm", "Trails Open (#)": "21",
          "Lifts Open (#)": "2", "Carpets Open (#)": "2", "Surface Conditions": "Packed Powder",
          "24 Hours (in)": "4", "48 Hours (in)": "7.5", "72 Hours (in)": "9", "Month to Date (in)": "30",
          "Season to Date (in)": "41", "Douglas - Open?": "Open", "Douglas Top Snow Depth": "38\"",
          "Marmot - Open?": "Open", "Coyote - Open?": "Closed", "Gray Butte - Open?": "Wind hold",
          "Local Timestamp": "2026-12-19 07:42:10", "Local Date": "2026-12-19"}


def sheet(**changes: str) -> str:
    """The saved sheet with one made-up report under its headings."""
    headings = next(csv.reader(io.StringIO(SHEET)))
    report = {**REPORT, **changes}
    assert set(report) <= set(headings)
    # The sheet's headings end in stray dates before "Local Timestamp": each cell is filled by where it stands.
    row = [report.get(name, "") if headings.index(name) == at else "" for at, name in enumerate(headings)]
    out = io.StringIO()
    csv.writer(out).writerows([headings, ["1/1/2026 8:00:00"] + [""] * (len(headings) - 1), row])
    return out.getvalue()


def test_the_sheet_before_the_season_gives_no_lifts_and_no_snow_report():
    feed = shastaskipark.parse(SHEET, NOW)
    assert feed == {"Name": "Mt. Shasta Ski Park", "LastUpdate": "2026-11-24T18:00:00Z",
                    "MountainAreas": [{"Name": "Mt. Shasta Ski Park", "Lifts": [], "Trails": []}]}


def test_a_report_gives_the_four_chairlifts_in_its_words():
    feed = shastaskipark.parse(sheet(), NOW)
    lifts = feed["MountainAreas"][0]["Lifts"]
    assert len(feed["MountainAreas"]) == 1 and feed["MountainAreas"][0]["Trails"] == []
    assert [(lift["Name"], lift["Status"], lift["StatusEnglish"]) for lift in lifts] == [
        ("Douglas", "Open", "open"), ("Marmot", "Open", "open"), ("Coyote", "Closed", "closed"),
        ("Gray Butte", "Wind hold", "wind hold")]
    assert lifts[0] == {"Name": "Douglas", "Status": "Open", "StatusEnglish": "open", "Difficulty": None}
    lifts = shastaskipark.parse(sheet(**{"Douglas - Open?": "Yes", "Marmot - Open?": "NO"}), NOW)["MountainAreas"][0]
    assert [lift["Status"] for lift in lifts["Lifts"]][:2] == ["Open", "Closed"]


def test_a_report_gives_the_depth_at_the_top_of_douglas_and_when_it_was_filed():
    snow = shastaskipark.parse(sheet(), NOW)["SnowReport"]
    # 7:42 in the morning, eight hours behind UTC in December.
    assert snow["LastUpdate"] == "2026-12-19T15:42:10Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Top of Douglas", "BaseIn": 38, "Last24HoursIn": 4, "Last48HoursIn": 7.5,
                                "Last72HoursIn": 9}
    assert snow["SeasonTotalIn"] == 41 and snow["BaseConditions"] == "Packed Powder"
    undated = shastaskipark.parse(sheet(**{"Local Timestamp": "this morning"}), NOW)["SnowReport"]
    assert undated["LastUpdate"] is None and undated["BaseArea"]["BaseIn"] == 38


def test_a_sheet_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="report's headings"):
        shastaskipark.parse("<!DOCTYPE html><html><body>Sign in</body></html>", NOW)
    with pytest.raises(ValueError, match="report's headings"):
        shastaskipark.parse("", NOW)
    with pytest.raises(ValueError, match="missing \\['Coyote - Open\\?'\\]"):
        shastaskipark.parse(SHEET.replace("Coyote - Open?", "Coyote Status"), NOW)
    with pytest.raises(ValueError, match="whether Marmot is open"):
        shastaskipark.parse(sheet(**{"Marmot - Open?": ""}), NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = shastaskipark.parse(sheet(**{"Douglas Top Snow Depth": "plenty"}), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"][0]["Lifts"]) == 4
    assert "SnowReport" not in shastaskipark.parse(sheet(**{"Douglas Top Snow Depth": "", "24 Hours (in)": ""}), NOW)
