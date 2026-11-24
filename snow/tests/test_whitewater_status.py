import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import whitewater

FIXTURES = Path(__file__).parent / "fixtures"
# The two pages' main parts with their scripts, styles, drawings and pictures taken out, and the statuses as they
# came; the reader gives the same on the whole pages.
PAGES = {name: (FIXTURES / f"whitewater_{name}.{'json' if name == 'status' else 'html'}").read_text()
         for name in whitewater.URLS}
NOW = datetime(2026, 11, 25, 1, 0, tzinfo=timezone.utc)


def page(name: str, old: str, new: str, count: int = -1) -> dict:
    assert old in PAGES[name]
    return {**PAGES, name: PAGES[name].replace(old, new, count)}


def said(heading: str, mark: str, key: str, label: str) -> dict:
    """The pages with one row's status changed."""
    loaded = json.loads(PAGES["status"])
    loaded["lifts"][heading]["runs"][mark] = {"key": key, "label": label, "icon": key}
    return {**PAGES, "status": json.dumps(loaded)}


def test_the_closed_mountain_reads_its_lifts_and_the_runs_under_each_heading():
    # Whitewater's pages on 2026-11-24, before it opens: 5 lifts, all closed, and the 44 runs it grooms, which its
    # statuses, last updated on April 6, still give as ungroomed, which is open.
    feed = whitewater.parse(PAGES, NOW)
    assert feed["Name"] == "Whitewater" and feed["LastUpdate"] == "2026-11-25T01:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Whitewater", 5, 0), ("Raven", 0, 20), ("Summit", 0, 13), ("Glory", 0, 11)]
    lifts = feed["MountainAreas"][0]["Lifts"]
    assert [lift["Name"] for lift in lifts] == ["Raven Chair", "Silver King Chair", "Hummer Handle Tow",
                                                "Summit Chair", "Glory Chair"]
    assert lifts[0] == {"Name": "Raven Chair", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}
    assert {lift["StatusEnglish"] for lift in lifts} == {"closed"}
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    assert trails[0] == {"Name": "Little Mucker", "Status": "Open", "StatusEnglish": "open", "Difficulty": "Green",
                         "Grooming": "No"}
    assert len(trails) == 44 and {(trail["Status"], trail["Grooming"]) for trail in trails} == {("Open", "No")}
    assert {trail["Difficulty"] for trail in trails} == {"Green", "Blue", "Black"}
    # The Nordic trails, the avalanche closures and the parking lots are not read.
    names = {row["Name"] for area in feed["MountainAreas"] for row in area["Lifts"] + area["Trails"]}
    assert not names & {"Meadow Trail", "Blasters Ridge", "Lot 1"}


def test_the_snow_report_is_in_inches_from_the_page_s_centimetres():
    snow = whitewater.parse(PAGES, NOW)["SnowReport"]
    # "Updated on Nov 24, 2026 at 12:09" in Nelson's time, seven hours behind UTC.
    assert snow["LastUpdate"] == "2026-11-24T19:09:00Z" and snow["Resortwide"] is True
    # 32 cm of base; 3 cm overnight, 5 cm in 24 and 48 hours, 3 days and 7 days, and 71 cm this season.
    assert snow["BaseArea"] == {"Name": "Summit weather plot", "Last24HoursIn": 2.0, "Last48HoursIn": 2.0,
                                "Last72HoursIn": 2.0, "Last7DaysIn": 2.0, "BaseIn": 12.6, "OvernightIn": 1.2}
    assert snow["SeasonTotalIn"] == 28.0 and snow["BaseConditions"] is None
    evening = whitewater.parse(page("snow", "Updated on Nov 24, 2026 at 12:09", "Updated on Jan 5, 2027 at 18:30"), NOW)
    assert evening["SnowReport"]["LastUpdate"] == "2027-01-06T01:30:00Z"
    # The overnight snow is in the page's summary, not its report, and its absence costs only itself.
    without = whitewater.parse(page("snow", "snow-summary__item--overnight", "snow-summary__item--night"), NOW)
    assert "OvernightIn" not in without["SnowReport"]["BaseArea"]


def test_each_status_of_the_page_s_key_is_read():
    loaded = json.loads(PAGES["status"])
    loaded["lifts"]["terrain"]["runs"]["raven_chair"] = {"key": "open", "label": "Open", "icon": "checkmark"}
    loaded["lifts"]["terrain"]["runs"]["summit_chair"] = {"key": "standby", "label": "On Hold", "icon": "standby"}
    runs = loaded["lifts"]["silver_king_lift"]["runs"]
    runs["little_mucker"] = {"key": "fresh", "label": "Freshly Groomed", "icon": "fresh"}
    runs["yankee_girl"] = {"key": "groomed", "label": "Previously Groomed", "icon": "groomed"}
    runs["upper_sluice_box"] = {"key": "closed", "label": "Closed", "icon": "cross"}
    runs["lower_sluice_box"] = {"key": "standby", "label": "Unknown", "icon": "standby"}
    feed = whitewater.parse({**PAGES, "status": json.dumps(loaded)}, NOW)
    lifts = feed["MountainAreas"][0]["Lifts"]
    assert [(lift["Name"], lift["Status"], lift["StatusEnglish"]) for lift in lifts if lift["Status"] != "Closed"] == [
        ("Raven Chair", "Open", "open"), ("Summit Chair", "On hold", "on hold")]
    trails = {trail["Name"]: trail for trail in feed["MountainAreas"][1]["Trails"]}
    assert [(trails[name]["Status"], trails[name]["StatusEnglish"], trails[name]["Grooming"])
            for name in ("Little Mucker", "Yankee Girl", "Upper Sluice Box", "Lower Sluice Box")] == [
        ("Open", "open", "Yes"), ("Open", "open", "No"), ("Closed", "closed", "No"), ("Unknown", "unknown", "No")]


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="Little Mucker has a status the reader does not know: 'patrol'"):
        whitewater.parse(said("silver_king_lift", "little_mucker", "patrol", "Patrol"), NOW)
    with pytest.raises(ValueError, match="Glory Chair has a status the reader does not know: 'wind'"):
        whitewater.parse(said("terrain", "glory_chair", "wind", "Wind Hold"), NOW)
    with pytest.raises(ValueError, match="Little Mucker has no status"):
        whitewater.parse(page("status", "\"little_mucker\"", "\"little_miner\""), NOW)
    with pytest.raises(ValueError, match="Raven Chair has no status"):
        whitewater.parse(page("status", "\"terrain\"", "\"lifts\""), NOW)
    with pytest.raises(ValueError, match="statuses do not read"):
        whitewater.parse({**PAGES, "status": "<html>unavailable</html>"}, NOW)
    with pytest.raises(ValueError, match="difficulty the reader does not know: Expert - Double Black Diamond"):
        whitewater.parse(page("lifts", "Most Difficult - Black Diamond", "Expert - Double Black Diamond", 1), NOW)
    with pytest.raises(ValueError, match="Raven lists 20 runs but 19 were read"):
        whitewater.parse(page("lifts", "<span class=\"lifts-runs__status\" data-update-lift=\"silver_king_lift\" "
                              "data-update-run=\"little_mucker\">", "<span data-update-run=\"little_mucker\">"), NOW)
    with pytest.raises(ValueError, match="lists no lifts"):
        whitewater.parse(page("lifts", "data-update-lift=\"terrain\"", "data-update-lift=\"lifts\""), NOW)
    with pytest.raises(ValueError, match="lists no runs"):
        whitewater.parse(page("lifts", "<section class=\"lifts-runs__lift ", "<section class=\"runs__lift "), NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    for old, new in (("<span class=\"condition-field__value\">32</span>", "<span class=\"condition-field__value\">--</span>"),
                     ("Updated on Nov 24, 2026 at 12:09", "Updated today"), ("Current Base", "Snow Base"),
                     ("<section class=\"daily-snow-report", "<section class=\"snow-report"),
                     ("condition-field__unit\">CM</span>", "condition-field__unit\">IN</span>")):
        feed = whitewater.parse(page("snow", old, new), NOW)
        assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 4
