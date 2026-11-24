import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import silverstar

FIXTURES = Path(__file__).parent / "fixtures"
# The three reports as the API gave them.
PAGES = {name: (FIXTURES / f"silverstar_{name}.json").read_text() for name in silverstar.URLS}
NOW = datetime(2026, 11, 24, 23, 30, tzinfo=timezone.utc)


def changed(name: str, change) -> dict:
    rows = json.loads(PAGES[name])
    change(rows)
    return {**PAGES, name: json.dumps(rows)}


def test_the_closed_mountain_reads_its_lifts_and_alpine_trails_by_part_of_the_mountain():
    # SilverStar's reports on 2026-11-24, ten days before it opens: 10 lifts and 133 alpine trails, all closed.
    feed = silverstar.parse(PAGES, NOW)
    assert feed["Name"] == "SilverStar" and feed["LastUpdate"] == "2026-11-24T23:30:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Attridge - Alpine Trails", 1, 14), ("Comet - Alpine Trails", 2, 38), ("Silver Woods - Alpine Trails", 1, 16),
        ("Putnam Creek - Alpine Trails", 2, 62), ("Silver Queen - Beginner Area", 1, 3), ("Tube Town", 1, 0),
        ("Adventure Centre - Snowsports School Beginner Area", 1, 0), ("Discovery Zone - Beginner Area", 1, 0)]
    lifts = {lift["Name"]: lift for area in feed["MountainAreas"] for lift in area["Lifts"]}
    assert len(lifts) == 10 and {lift["StatusEnglish"] for lift in lifts.values()} == {"closed"}
    assert lifts["Comet Express"] == {"Name": "Comet Express", "Status": "Closed", "StatusEnglish": "closed",
                                      "Difficulty": None}
    assert lifts["Des Schumann Summit Express"]["Status"] == "Closed" and "Putnam Express" in lifts
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    # The cross-country, snowshoe, fat bike, biking and hiking trails and the hidden trails are not there.
    assert len(trails) == 133 < len(json.loads(PAGES["trails"]))
    assert trails[0] == {"Name": "Abbot's Gulch", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": "Blue",
                         "Grooming": "No"}
    assert {trail["Difficulty"] for trail in trails} == {"Green", "Blue", "Black", "Double black"}


def test_the_snow_report_is_the_newest_and_is_in_inches_from_the_report_s_centimetres():
    snow = silverstar.parse(PAGES, NOW)["SnowReport"]
    # Dated 2026-11-21 07:52:20 in British Columbia's time, seven hours behind UTC all year.
    assert snow["LastUpdate"] == "2026-11-21T14:52:20Z" and snow["Resortwide"] is True
    assert snow["BaseArea"]["BaseIn"] == 0 and snow["BaseArea"]["Last24HoursIn"] == 0 and snow["SeasonTotalIn"] == 0
    assert "Tentative Alpine Opening" in snow["Report"]

    def midwinter(rows):
        newest = max(rows, key=lambda row: row["date"])
        newest.update(base_depth=150, overnight_amount=5, computed={**newest["computed"], "24_hour": 12, "total": 310})
    snow = silverstar.parse(changed("snow", midwinter), NOW)["SnowReport"]
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": 59.1, "Last24HoursIn": 4.7, "Last48HoursIn": 0.0,
                                "Last72HoursIn": 0.0, "Last7DaysIn": 0.0, "OvernightIn": 2.0}
    assert snow["SeasonTotalIn"] == 122.0
    backwards = changed("snow", lambda rows: rows.reverse())
    assert silverstar.parse(backwards, NOW)["SnowReport"]["LastUpdate"] == "2026-11-21T14:52:20Z"


def test_a_lift_on_hold_and_a_groomed_open_trail_take_the_report_s_words():
    def hold(rows):
        rows[1]["status"] = "wind_hold"
    lift = silverstar.parse(changed("lifts", hold), NOW)["MountainAreas"][1]["Lifts"][0]
    assert (lift["Name"], lift["Status"], lift["StatusEnglish"]) == ("Comet Express", "Wind hold", "wind hold")

    def groomed(rows):
        row = next(row for row in rows if row["name"] == "Abbot's Gulch")
        row.update(status="open", groom_status="groomed")
    feed = silverstar.parse(changed("trails", groomed), NOW)
    trail = next(t for area in feed["MountainAreas"] for t in area["Trails"] if t["Name"] == "Abbot's Gulch")
    assert (trail["StatusEnglish"], trail["Grooming"]) == ("open", "Yes")


def test_a_report_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="not a list"):
        silverstar.parse({**PAGES, "lifts": "{}"}, NOW)
    with pytest.raises(ValueError, match="does not read as JSON"):
        silverstar.parse({**PAGES, "trails": "<html>"}, NOW)
    with pytest.raises(ValueError, match="lists no lifts"):
        silverstar.parse({**PAGES, "lifts": "[]"}, NOW)
    with pytest.raises(ValueError, match="difficulty the reader does not know"):
        silverstar.parse(changed("trails", lambda rows: [row.update(difficulty="hardest") for row in rows]), NOW)
    with pytest.raises(ValueError, match="not in the shape expected"):
        silverstar.parse(changed("lifts", lambda rows: rows[0].pop("sector")), NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    def feet(rows):
        for row in rows:
            row["unit_of_measurement"] = "ft"
    feed = silverstar.parse(changed("snow", feet), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 8
    assert "SnowReport" not in silverstar.parse({**PAGES, "snow": "[]"}, NOW)
    assert "SnowReport" not in silverstar.parse(changed("snow", lambda rows: [row.pop("computed") for row in rows]), NOW)
