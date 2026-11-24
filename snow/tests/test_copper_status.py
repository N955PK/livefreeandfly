import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import copper

FIXTURES = Path(__file__).parent / "fixtures"
# The three reports as the API gave them, but for the snow reports' author fields, which are taken out.
PAGES = {name: (FIXTURES / f"copper_{name}.json").read_text() for name in copper.URLS}
NOW = datetime(2026, 11, 24, 18, 0, tzinfo=timezone.utc)


def changed(name: str, change) -> dict:
    rows = json.loads(PAGES[name])
    change(rows)
    return {**PAGES, name: json.dumps(rows)}


def test_the_early_season_mountain_reads_its_three_open_lifts_by_part_of_the_mountain():
    # Copper's reports on 2026-11-24, early season: 23 lifts with three open, 166 ski trails and parks with six open.
    feed = copper.parse(PAGES, NOW)
    assert feed["Name"] == "Copper Mountain" and feed["LastUpdate"] == "2026-11-24T18:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("East", 3, 18), ("Copper Bowl", 2, 13), ("Tucker Mountain", 1, 10), ("Spaulding & Resolution", 2, 23),
        ("Union Peak", 3, 16), ("Beginner Learning", 3, 2), ("Center", 3, 43), ("West", 6, 32),
        ("Woodward Mountain Park", 0, 9)]
    lifts = {lift["Name"]: lift for area in feed["MountainAreas"] for lift in area["Lifts"]}
    assert len(lifts) == 23
    assert sorted(name for name, lift in lifts.items() if lift["StatusEnglish"] == "open") == [
        "American Eagle", "American Flyer", "Easy Rider"]
    assert lifts["American Flyer"] == {"Name": "American Flyer", "Status": "Open", "StatusEnglish": "open",
                                       "Difficulty": None}
    assert lifts["Super Bee"]["Status"] == "Closed" and lifts["Timberline Express"]["Status"] == "Closed"
    trails = {trail["Name"]: trail for area in feed["MountainAreas"] for trail in area["Trails"]}
    assert sorted(name for name, trail in trails.items() if trail["StatusEnglish"] == "open") == [
        "EZ Rider/Learning Area", "Fair Play", "High Point", "Loverly", "Main Vein", "Rhapsody"]
    assert trails["Rhapsody"] == {"Name": "Rhapsody", "Status": "Open", "StatusEnglish": "open", "Difficulty": "Blue",
                                  "Grooming": "Yes"}
    assert trails["Far East"]["Difficulty"] == "Black" and trails["Far East"]["Grooming"] == "No"
    # The summer biking and hiking trails, the uphill and cross-country routes and the hidden trails are not there.
    assert sum(len(area["Trails"]) for area in feed["MountainAreas"]) == 166 < len(json.loads(PAGES["trails"]))
    assert {trail["Difficulty"] for trail in trails.values()} == {"Green", "Blue", "Black", "Double black"}


def test_the_snow_report_is_the_newest_with_its_depth_snowfall_and_when_it_was_posted():
    snow = copper.parse(PAGES, NOW)["SnowReport"]
    # Dated 05:00 Mountain standard time.
    assert snow["LastUpdate"] == "2026-11-24T12:00:00Z" and snow["Resortwide"] is True
    assert snow["BaseConditions"] is None and snow["SeasonTotalIn"] == 14
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": 18, "Last24HoursIn": 1, "Last48HoursIn": 1,
                                "Last72HoursIn": 3, "Last7DaysIn": 8, "OvernightIn": 1}
    assert "New snow overnight" in snow["Report"]
    backwards = changed("snow", lambda rows: rows.reverse())
    assert copper.parse(backwards, NOW)["SnowReport"] == snow


def test_a_lift_on_hold_takes_the_report_s_words():
    def hold(rows):
        rows[0]["status"] = "wind_hold"
    lift = copper.parse(changed("lifts", hold), NOW)["MountainAreas"][0]["Lifts"][0]
    assert (lift["Name"], lift["Status"], lift["StatusEnglish"]) == ("Super Bee", "Wind hold", "wind hold")


def test_an_all_closed_mountain_reads_as_closed():
    def shut(rows):
        for row in rows:
            row["status"] = "closed"
    feed = copper.parse({**changed("lifts", shut), "trails": changed("trails", shut)["trails"]}, NOW)
    rows = [row for area in feed["MountainAreas"] for row in area["Lifts"] + area["Trails"]]
    assert len(rows) == 189 and {row["StatusEnglish"] for row in rows} == {"closed"}


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    def metric(rows):
        rows[0]["unit_of_measurement"] = "cm"
    feed = copper.parse(changed("snow", metric), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 9
    assert "SnowReport" not in copper.parse({**PAGES, "snow": "[]"}, NOW)
    assert "SnowReport" not in copper.parse(changed("snow", lambda rows: rows[0].update(base_depth="18")), NOW)


def test_reports_that_are_missing_or_changed_are_refused():
    with pytest.raises(ValueError, match="does not read as JSON"):
        copper.parse({**PAGES, "lifts": "<html>"}, NOW)
    with pytest.raises(ValueError, match="not a list"):
        copper.parse({**PAGES, "trails": "{}"}, NOW)
    with pytest.raises(ValueError, match="lists no lifts"):
        copper.parse({**PAGES, "lifts": "[]"}, NOW)
    with pytest.raises(ValueError, match="lists no trails"):
        copper.parse({**PAGES, "trails": "[]"}, NOW)
    with pytest.raises(ValueError, match="not in the shape expected"):
        copper.parse(changed("lifts", lambda rows: rows[0].pop("sector")), NOW)
    with pytest.raises(ValueError, match="difficulty the reader does not know"):
        copper.parse(changed("trails", lambda rows: rows[0].update(difficulty="hardest")), NOW)
    with pytest.raises(ValueError, match="grooming the reader does not know"):
        copper.parse(changed("trails", lambda rows: rows[0].update(groom_status="maybe")), NOW)
    with pytest.raises(ValueError, match="has no status"):
        copper.parse(changed("lifts", lambda rows: rows[0].update(status=None)), NOW)
