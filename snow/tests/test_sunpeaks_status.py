from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import sunpeaks

FIXTURES = Path(__file__).parent / "fixtures"
# Both pages with their scripts, styles and drawings taken out, and a staff member's name from a notice; the reader
# gives the same on the whole pages.
PAGES = {name: (FIXTURES / f"sunpeaks_{name}.html").read_text() for name in sunpeaks.URLS}
NOW = datetime(2026, 11, 24, 23, 30, tzinfo=timezone.utc)


def page(name: str, old: str, new: str, count: int = -1) -> dict:
    assert old in PAGES[name]
    return {**PAGES, name: PAGES[name].replace(old, new, count)}


def test_the_closed_mountain_reads_its_lifts_and_its_trails_by_zone():
    # Sun Peaks' pages on 2026-11-24, two days before it opens: 12 lifts and 157 trails, all closed.
    feed = sunpeaks.parse(PAGES, NOW)
    assert feed["Name"] == "Sun Peaks" and feed["LastUpdate"] == "2026-11-24T23:30:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Sun Peaks", 12, 0), ("Mt. Morrisey", 0, 23), ("West Bowl", 0, 7), ("Orient Ridge", 0, 15),
        ("Sundance", 0, 28), ("Tod Mountain", 0, 84)]
    lifts = {lift["Name"]: lift for lift in feed["MountainAreas"][0]["Lifts"]}
    assert lifts["Sunburst Express Chairlift"] == {"Name": "Sunburst Express Chairlift", "Status": "Closed",
                                                   "StatusEnglish": "closed", "Difficulty": None}
    assert lifts["Burfield Chairlift"]["Status"] == "Closed" and "West Bowl Express Chairlift" in lifts
    trails = {trail["Name"]: trail for area in feed["MountainAreas"] for trail in area["Trails"]}
    assert len(trails) == 157 and {trail["StatusEnglish"] for trail in trails.values()} == {"closed"}
    assert trails["5 Mile Lower"] == {"Name": "5 Mile Lower", "Status": "Closed", "StatusEnglish": "closed",
                                      "Difficulty": "Green", "Grooming": "No"}
    assert trails["Challenger"]["Difficulty"] == "Double black" and trails["Bling Glades"]["Difficulty"] == ""
    assert {trail["Difficulty"] for trail in trails.values()} == {"Green", "Blue", "Black", "Double black", ""}
    assert "Anticipation" in {trail["Name"] for trail in feed["MountainAreas"][1]["Trails"]}


def test_the_snow_report_is_in_inches_from_the_page_s_centimetres():
    snow = sunpeaks.parse(PAGES, NOW)["SnowReport"]
    # "Updated November 24th at 4:13pm", seven hours behind UTC, in the year of the reading.
    assert snow["LastUpdate"] == "2026-11-24T23:13:00Z" and snow["Resortwide"] is False
    # 29 cm at mid-mountain and 35 cm in the alpine; 8 cm in 24 hours, 48 hours and 7 days. The figures the page
    # keeps in comments (a 6 cm, a 7 cm, a 19 cm) are not read.
    assert snow["MidMountainArea"] == {"Name": "Mid Mountain", "BaseIn": 11.4, "Last24HoursIn": 3.1,
                                       "Last48HoursIn": 3.1, "Last7DaysIn": 3.1}
    assert snow["SummitArea"] == {"Name": "Alpine", "BaseIn": 13.8}
    assert snow["BaseConditions"] is None and "BaseArea" not in snow
    # A report dated later in the year than the reading is last year's.
    january = datetime(2027, 1, 2, 18, 0, tzinfo=timezone.utc)
    assert sunpeaks.parse(PAGES, january)["SnowReport"]["LastUpdate"] == "2026-11-24T23:13:00Z"


def test_open_and_groomed_rows_are_read_in_the_words_of_the_page_s_key():
    closed = "<span class=\"icon-close\"></span>\n    </div>\n</article>"
    pages = page("lifts", closed, "<span class=\"icon-open\"></span>\n    </div>\n</article>", 13)
    pages = {**pages, "lifts": pages["lifts"].replace(closed, "<span class=\"icon-tick groomed\"></span>\n    </div>\n"
                                                      "</article>", 1)
             .replace(closed, "<span class=\"icon-tick groomed-with-fresh\"></span>\n    </div>\n</article>", 1)}
    feed = sunpeaks.parse(pages, NOW)
    assert {lift["StatusEnglish"] for lift in feed["MountainAreas"][0]["Lifts"]} == {"open"}
    trails = {trail["Name"]: trail for area in feed["MountainAreas"] for trail in area["Trails"]}
    assert [(t["Name"], t["Status"], t["Grooming"]) for t in list(trails.values()) if t["StatusEnglish"] == "open"] == [
        ("Anticipation", "Open", "Yes"), ("5 Mile Lower", "Open", "No"), ("5 Mile Upper", "Open", "Yes")]


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="status symbols"):
        sunpeaks.parse(page("lifts", "<span class=\"icon-close\"></span>\n    </div>\n</article>",
                            "<span class=\"icon-hold\"></span>\n    </div>\n</article>", 1), NOW)
    with pytest.raises(ValueError, match="difficulty symbols"):
        sunpeaks.parse(page("lifts", "icon-trail_4-experts-only", "icon-trail_7-extreme"), NOW)
    with pytest.raises(ValueError, match="zones were not found"):
        sunpeaks.parse(page("lifts", "<select id=\"zone\"", "<select id=\"area\""), NOW)
    with pytest.raises(ValueError, match="is in zones \\[\\], not one"):
        sunpeaks.parse(page("lifts", "iso-item cat-west-bowl", "iso-item cat-east-bowl", 1), NOW)
    with pytest.raises(ValueError, match="counts 13 lifts but 12"):
        sunpeaks.parse(page("lifts", "lifts-total\">/12<", "lifts-total\">/13<"), NOW)
    with pytest.raises(ValueError, match="counts 200 trails but only 157"):
        sunpeaks.parse(page("lifts", "trails-total\">/144<", "trails-total\">/200<"), NOW)
    with pytest.raises(ValueError, match="no lifts or no trails"):
        sunpeaks.parse(page("lifts", "node-type-lift", "node-type-ride"), NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    for old, new in (("<h4>Alpine</h4>", "<h4>Summit</h4>"), ("Updated November 24th at 4:13pm", "Updated today"),
                     ("id=\"snow-conditions\"", "id=\"snow\""), ("<h4>24 Hr</h4>", "<h4>Day</h4>")):
        feed = sunpeaks.parse(page("snow", old, new), NOW)
        assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 6
