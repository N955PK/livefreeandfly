from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import norquay

# The page from the day's update to the end of its lift and run status, with its scripts, styles and drawings and
# the page builder's settings taken out; the reader gives the same on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "norquay_conditions.html").read_text()
NOW = datetime(2026, 11, 24, 23, 40, tzinfo=timezone.utc)
RUN_CLOSED = "<span class=\"run-status status-closed\"></span>"


def page(old: str, new: str, count: int = -1) -> str:
    assert old in PAGE
    return PAGE.replace(old, new, count)


def test_the_early_season_mountain_reads_each_lift_with_the_runs_under_it():
    # Norquay on 2026-11-24: 2 of 6 lifts and 3 of 79 runs open.
    feed = norquay.parse(PAGE, NOW)
    assert feed["Name"] == "Mt. Norquay" and feed["LastUpdate"] == "2026-11-24T23:40:00Z"
    assert [(area["Name"], area["Lifts"][0]["Status"], len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("North American Chair", "Closed", 25), ("Spirit Chair", "Closed", 14), ("Sundance Carpet", "Open", 1),
        ("Cascade Chair", "Open", 7), ("Mystic Chair", "Closed", 31), ("Rundle Carpet", "Closed", 1)]
    areas = {area["Name"]: area for area in feed["MountainAreas"]}
    assert all(len(area["Lifts"]) == 1 for area in areas.values())
    assert areas["Cascade Chair"]["Lifts"] == [{"Name": "Cascade Chair", "Status": "Open", "StatusEnglish": "open",
                                                "Difficulty": None}]
    assert areas["Sundance Carpet"]["Trails"] == [{"Name": "Sundance", "Status": "Open", "StatusEnglish": "open",
                                                   "Difficulty": "Green", "Grooming": "Yes"}]
    assert areas["North American Chair"]["Trails"][0] == {"Name": "North American", "Status": "Closed",
                                                          "StatusEnglish": "closed", "Difficulty": "Black",
                                                          "Grooming": "No"}
    trails = [trail for area in areas.values() for trail in area["Trails"]]
    assert [trail["Name"] for trail in trails if trail["StatusEnglish"] == "open"] == ["Sundance", "Zoomer", "Cascade"]
    assert {trail["Difficulty"] for trail in trails} == {"Green", "Blue", "Black"}
    # The tube park is listed after the lifts and is not one.
    assert "Tube Park" in PAGE and "Tube Park" not in areas


def test_the_snow_report_is_in_inches_from_the_page_s_centimetres():
    snow = norquay.parse(PAGE, NOW)["SnowReport"]
    # "Conditions update for Tuesday, November 24.": the start of that day in Alberta, six hours behind UTC.
    assert snow["LastUpdate"] == "2026-11-24T06:00:00Z" and snow["Resortwide"] is False
    # Nothing overnight or in 24 hours and 6 cm in 7 days; 30 cm of base low down and 35 cm up high; 32 cm this year.
    assert snow["BaseArea"] == {"Name": "Lower Mountain", "OvernightIn": 0.0, "Last24HoursIn": 0.0,
                                "Last7DaysIn": 2.4, "BaseIn": 11.8}
    assert snow["SummitArea"] == {"Name": "Upper Mountain", "BaseIn": 13.8}
    assert snow["SeasonTotalIn"] == 12.6 and snow["BaseConditions"] is None


def test_the_day_of_the_update_takes_the_year_that_does_not_put_it_ahead():
    january = datetime(2027, 1, 2, 18, 0, tzinfo=timezone.utc)
    late = page("Conditions update for Tuesday, November 24.", "Conditions update for Thursday, December 31st.")
    assert norquay.parse(late, january)["SnowReport"]["LastUpdate"] == "2026-12-31T06:00:00Z"
    # A page that does not head its update with a day has an undated report, which the runner treats as old once
    # no lift is turning.
    unheaded = page("Conditions update for Tuesday, November 24.", "Welcome back.")
    assert norquay.parse(unheaded, NOW)["SnowReport"]["LastUpdate"] is None


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="lift and run status was not found"):
        norquay.parse(page("id=\"liftstatus\"", "id=\"lifts\""), NOW)
    with pytest.raises(ValueError, match="Cascade Chair has a status the reader does not know: 'Wind Hold'"):
        norquay.parse(page("Cascade Chair <span class=\"lift-status is-open\">Open</span>",
                           "Cascade Chair <span class=\"lift-status is-hold\">Wind Hold</span>"), NOW)
    with pytest.raises(ValueError, match="North American has a status the reader does not know: shut"):
        norquay.parse(page(RUN_CLOSED, "<span class=\"run-status status-shut\"></span>", 1), NOW)
    with pytest.raises(ValueError, match="North American has a difficulty the reader does not know: extreme"):
        norquay.parse(page("run-difficulty difficulty-advanced", "run-difficulty difficulty-extreme", 1), NOW)
    with pytest.raises(ValueError, match="North American has a grooming the reader does not know: winched"):
        norquay.parse(page("run-groomed groomed-ungroomed", "run-groomed groomed-winched", 1), NOW)
    with pytest.raises(ValueError, match="counts 3 open runs but 4"):
        norquay.parse(page(RUN_CLOSED, "<span class=\"run-status status-open\"></span>", 1), NOW)
    # A run's row that has lost its shape is missed, and its lift's count of rows shows it.
    with pytest.raises(ValueError, match="North American Chair lists 25 runs but 24"):
        norquay.parse(page("<span class=\"run-groomed groomed-ungroomed\"></span>",
                           "<i class=\"run-groomed groomed-ungroomed\"></i>", 1), NOW)
    with pytest.raises(ValueError, match="lists 6 lifts but 5"):
        norquay.parse(page("Spirit Chair <span class=\"lift-status is-closed\">Closed</span>",
                           "Spirit Chair <b class=\"lift-status is-closed\">Closed</b>"), NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    for old, new in (("Current Snowfall</h3>", "Snowfall</h3>"), (">30cm<", ">30in<"),
                     (">Last 24 Hours<", ">Since Yesterday<"), (">Upper Mountain<", ">Summit<")):
        feed = norquay.parse(page(old, new), NOW)
        assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 6
