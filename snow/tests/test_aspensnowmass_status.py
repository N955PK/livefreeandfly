import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import aspensnowmass

FIXTURES = Path(__file__).parent / "fixtures"
# The twelve reports as the site gave them on 2026-11-26, before the lifts turned on Aspen Mountain's and
# Snowmass's opening day.
PAGES = {name: (FIXTURES / f"aspensnowmass_{name}.json").read_text() for name in aspensnowmass.URLS}
NOW = datetime(2026, 11, 26, 14, 0, tzinfo=timezone.utc)


def changed(name: str, change) -> dict:
    found = json.loads(PAGES[name])
    change(found)
    return {**PAGES, name: json.dumps(found)}


def rows(feed: dict, kind: str) -> list:
    return [row for area in feed["MountainAreas"] for row in area[kind]]


def test_each_mountain_asks_the_site_s_three_reports_by_its_own_name():
    assert list(aspensnowmass.MOUNTAINS) == ["aspen", "highlands", "buttermilk", "snowmass"]
    assert len(aspensnowmass.URLS) == 12
    assert aspensnowmass.URLS["aspen_lifts"] == ("https://www.aspensnowmass.com/AspenSnowmass/LiftStatus/Feed"
                                                 "?mountain=AspenMountain&areas=&isSummer=False")
    assert aspensnowmass.URLS["highlands_trails"] == ("https://www.aspensnowmass.com/AspenSnowmass/GroomingReport/Feed"
                                                      "?mountain=AspenHighlands")
    assert aspensnowmass.URLS["snowmass_snow"] == ("https://www.aspensnowmass.com/AspenSnowmass/SnowReport/Feed"
                                                   "?mountain=Snowmass")


def test_the_four_mountains_are_read_each_under_its_own_key():
    feeds = aspensnowmass.parse(PAGES, NOW)
    assert list(feeds) == ["aspen", "highlands", "buttermilk", "snowmass"]
    assert [feed["Name"] for feed in feeds.values()] == ["Aspen Mountain", "Aspen Highlands", "Buttermilk", "Snowmass"]
    assert {feed["LastUpdate"] for feed in feeds.values()} == {"2026-11-26T14:00:00Z"}
    assert {key: (len(rows(feed, "Lifts")), len(rows(feed, "Trails"))) for key, feed in feeds.items()} == {
        "aspen": (6, 139), "highlands": (5, 124), "buttermilk": (5, 49), "snowmass": (20, 130)}
    # Before the lifts turn every lift is closed; Aspen Mountain's first trails are already marked open and groomed.
    assert {lift["StatusEnglish"] for feed in feeds.values() for lift in rows(feed, "Lifts")} == {"closed"}
    assert sorted(trail["Name"] for trail in rows(feeds["aspen"], "Trails") if trail["StatusEnglish"] == "open") == [
        "Deer Park", "Dipsy Doodle (Lower)", "Dipsy Doodle (Upper)", "Easy Chair", "Silver Bell"]
    assert not [trail for trail in rows(feeds["snowmass"], "Trails") if trail["StatusEnglish"] == "open"]


def test_a_mountain_s_lifts_and_trails_are_placed_by_part_of_the_mountain():
    feed = aspensnowmass.mountain("aspen", PAGES, NOW)
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Hero's", 1, 33), ("Lower Mountain", 2, 4), ("Upper Mountain", 3, 0), ("Ajax Express", 0, 21),
        ("F.I.S.", 0, 14), ("Gated Areas", 0, 4), ("Ruthie's", 0, 9), ("Shadow Mountain", 0, 27),
        ("Silver Queen", 0, 27)]
    areas = {area["Name"]: area for area in feed["MountainAreas"]}
    assert areas["Lower Mountain"]["Lifts"] == [
        {"Name": "Nell Bell", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None},
        {"Name": "Silver Queen Gondola", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}]
    trails = {trail["Name"]: trail for trail in rows(feed, "Trails")}
    assert trails["Deer Park"] == {"Name": "Deer Park", "Status": "Open", "StatusEnglish": "open",
                                   "Difficulty": "Blue", "Grooming": "Yes"}
    assert {trail["Difficulty"] for trail in trails.values()} == {"Blue", "Black", "Double black"}
    # The uphill routes are not part of the lift-served mountain.
    assert "Uphill Routes" not in areas
    snowmass = aspensnowmass.mountain("snowmass", PAGES, NOW)
    assert {trail["Difficulty"] for trail in rows(snowmass, "Trails")} == {"Green", "Blue", "Black", "Double black", ""}
    assert [area["Name"] for area in snowmass["MountainAreas"] if area["Lifts"]] == [
        "Alpine Springs", "Big Burn", "Campground", "Coney Express", "Elk Camp", "High Alpine", "Sam's Knob",
        "Two Creeks"]


def test_the_snow_report_gives_the_base_depth_the_snowfall_and_when_it_was_posted():
    feeds = aspensnowmass.parse(PAGES, NOW)
    snow = feeds["snowmass"]["SnowReport"]
    # "06:47 AM Nov 26, 2026", seven hours behind UTC in November.
    assert snow["LastUpdate"] == "2026-11-26T13:47:00Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": 19, "Last24HoursIn": 0, "Last48HoursIn": 2,
                                "Last72HoursIn": 2, "Last7DaysIn": 11}
    assert snow["BaseConditions"] is None and snow["SeasonTotalIn"] is None
    assert snow["Report"].startswith("Snowmass opens for the 2026-2027 winter season") and "<" not in snow["Report"]
    assert feeds["aspen"]["SnowReport"]["BaseArea"]["BaseIn"] == 13
    assert feeds["aspen"]["SnowReport"]["LastUpdate"] == "2026-11-26T13:44:00Z"
    # Highlands and Buttermilk, not yet open, report no base.
    assert feeds["highlands"]["SnowReport"]["BaseArea"]["BaseIn"] == 0


def test_a_lift_on_hold_or_open_takes_the_report_s_words():
    def hold(found):
        found["liftStatuses"][0]["status"] = "On Hold"
        found["liftStatuses"][1]["status"] = "Open"
    lifts = rows(aspensnowmass.mountain("snowmass", changed("snowmass_lifts", hold), NOW), "Lifts")
    assert (lifts[0]["Name"], lifts[0]["Status"], lifts[0]["StatusEnglish"]) == ("Alpine Springs", "On hold", "on hold")
    assert (lifts[1]["Name"], lifts[1]["Status"], lifts[1]["StatusEnglish"]) == ("Big Burn", "Open", "open")


def test_one_mountain_that_cannot_be_read_costs_none_of_the_others():
    feeds = aspensnowmass.parse({**PAGES, "buttermilk_lifts": "<html>"}, NOW)
    assert list(feeds) == ["aspen", "highlands", "snowmass"]
    missing = {name: page for name, page in PAGES.items() if not name.startswith("highlands")}
    assert list(aspensnowmass.parse(missing, NOW)) == ["aspen", "buttermilk", "snowmass"]
    with pytest.raises(ValueError, match="Aspen Mountain: .*Snowmass: "):
        aspensnowmass.parse({name: "<html>" for name in PAGES}, NOW)


def test_reports_that_are_missing_or_changed_are_refused():
    with pytest.raises(ValueError, match="does not read as JSON"):
        aspensnowmass.mountain("aspen", {**PAGES, "aspen_lifts": "<html>"}, NOW)
    with pytest.raises(ValueError, match="not in the shape expected"):
        aspensnowmass.mountain("aspen", {**PAGES, "aspen_trails": "[]"}, NOW)
    with pytest.raises(ValueError, match="lists no lifts"):
        aspensnowmass.mountain("aspen", changed("aspen_lifts", lambda found: found["liftStatuses"].clear()), NOW)
    with pytest.raises(ValueError, match="lists no trails"):
        aspensnowmass.mountain("aspen", changed("aspen_trails", lambda found: found["areas"].clear()), NOW)
    with pytest.raises(ValueError, match="status the reader does not know"):
        aspensnowmass.mountain("aspen", changed("aspen_lifts",
                                                lambda found: found["liftStatuses"][0].update(status="Delayed")), NOW)
    with pytest.raises(ValueError, match="difficulty the reader does not know"):
        aspensnowmass.mountain("aspen", changed(
            "aspen_trails", lambda found: found["areas"][0]["trails"][0].update(difficulty="hardest")), NOW)
    with pytest.raises(ValueError, match="open and groomed"):
        aspensnowmass.mountain("aspen", changed(
            "aspen_trails", lambda found: found["areas"][0]["trails"][0].update(isDayOpen=None)), NOW)
    with pytest.raises(ValueError, match="no name"):
        aspensnowmass.mountain("aspen", changed("aspen_lifts", lambda found: found["liftStatuses"][0].pop("area")), NOW)
    with pytest.raises(ValueError, match="counts 7 lifts but 6"):
        aspensnowmass.mountain("aspen", changed("aspen_snow", lambda found: found["lifts"].update(totalCount=7)), NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = aspensnowmass.mountain("aspen", {**PAGES, "aspen_snow": "<html>"}, NOW)
    assert "SnowReport" not in feed and len(rows(feed, "Lifts")) == 6
    undated = changed("aspen_snow", lambda found: found.update(lastUpdated=None))
    assert "SnowReport" not in aspensnowmass.mountain("aspen", undated, NOW)
    metric = changed("aspen_snow", lambda found: found["snowBase"].pop("inches"))
    assert "SnowReport" not in aspensnowmass.mountain("aspen", metric, NOW)
