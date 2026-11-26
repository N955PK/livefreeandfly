from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import fortyninenorth

FIXTURES = Path(__file__).parent / "fixtures"
# Both pages with their scripts, styles, drawings and comments taken out; the reader gives the same on the whole pages.
PAGES = {name: (FIXTURES / f"fortyninenorth_{name}.html").read_text() for name in fortyninenorth.URLS}
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)
CLOSED = "Closed\n\t                                </span></h4>"


def lifts_page(old: str, new: str, count: int = -1) -> dict:
    assert old in PAGES["lifts"]
    return {**PAGES, "lifts": PAGES["lifts"].replace(old, new, count)}


def snow_page(old: str, new: str, count: int = -1) -> dict:
    assert old in PAGES["snow"]
    return {**PAGES, "snow": PAGES["snow"].replace(old, new, count)}


def test_the_preseason_mountain_reads_its_lifts_and_each_part_s_trails():
    # 49 Degrees North's pages on 2026-11-26, before opening: seven lifts and 87 trails, all closed.
    feed = fortyninenorth.parse(PAGES, NOW)
    assert feed["Name"] == "49 Degrees North" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Lifts", 7, 0), ("Sunrise Basin", 0, 17), ("Sunrise Basin Glades", 0, 3), ("Central Basin", 0, 40),
        ("Central Basin Glades", 0, 2), ("West Basin", 0, 25)]
    assert [lift["Name"] for lift in feed["MountainAreas"][0]["Lifts"]] == [
        "Northern Spirit #1", "Grub stake #2", "Payday #3", "Silver Lode #4", "Angel Peak #6", "Sunrise Quad #5",
        "Gold Fever Conveyor #7"]
    assert feed["MountainAreas"][0]["Lifts"][0] == {"Name": "Northern Spirit #1", "Status": "Closed",
                                                    "StatusEnglish": "closed", "Difficulty": None}
    assert feed["MountainAreas"][1]["Trails"][0] == {"Name": "Alpine Road", "Status": "Closed",
                                                     "StatusEnglish": "closed", "Difficulty": None}
    rows = [row for area in feed["MountainAreas"] for row in area["Lifts"] + area["Trails"]]
    assert len(rows) == 94 and {row["StatusEnglish"] for row in rows} == {"closed"}
    # A name with a dash of its own is kept whole.
    assert "Ben-Andras Way" in {row["Name"] for row in rows}


def test_the_snow_report_gives_the_base_and_the_summit_and_when_it_was_updated():
    snow = fortyninenorth.parse(PAGES, NOW)["SnowReport"]
    # "Last updated: 11/24/26 at 12:11pm", eight hours behind UTC in November.
    assert snow["LastUpdate"] == "2026-11-24T20:11:00Z" and snow["Resortwide"] is True
    # The page leaves both depths empty before the mountain opens.
    assert snow["BaseArea"] == {"Name": "Base", "Last12HoursIn": 2, "Last24HoursIn": 4, "Last48HoursIn": 4,
                                "Last72HoursIn": 4, "BaseIn": None}
    assert snow["SummitArea"] == {"Name": "Summit", "Last12HoursIn": 3, "Last24HoursIn": 6, "Last48HoursIn": 6,
                                  "Last72HoursIn": 6, "BaseIn": None}
    assert snow["SeasonTotalIn"] == 12 and snow["BaseConditions"] is None


def test_a_depth_and_a_surface_are_read_when_the_page_has_them():
    assert PAGES["snow"].count('<h3>"</h3>') == 2
    filled = PAGES["snow"].replace('<h3>"</h3>', '<h3>38"</h3>', 1).replace('<h3>"</h3>', '<h3>61.5"</h3>', 1)
    assert "<h4>Surface Condition</h4>\n\t\t\t\t\t\t\t\t\t<h3></h3>" in filled
    filled = filled.replace("<h4>Surface Condition</h4>\n\t\t\t\t\t\t\t\t\t<h3></h3>",
                            "<h4>Surface Condition</h4><h3>Packed Powder</h3>")
    snow = fortyninenorth.parse({**PAGES, "snow": filled}, NOW)["SnowReport"]
    assert snow["BaseArea"]["BaseIn"] == 38 and snow["SummitArea"]["BaseIn"] == 61.5
    assert snow["BaseConditions"] == "Packed Powder"


def test_open_lifts_and_groomed_trails_are_read():
    pages = lifts_page(CLOSED, "Open\n</span></h4>", 9)
    pages = {**pages, "lifts": pages["lifts"].replace(CLOSED, "Groomed\n</span></h4>", 1)}
    feed = fortyninenorth.parse(pages, NOW)
    assert {lift["StatusEnglish"] for lift in feed["MountainAreas"][0]["Lifts"]} == {"open"}
    trails = feed["MountainAreas"][1]["Trails"]
    assert [trail["StatusEnglish"] for trail in trails[:4]] == ["open", "open", "open", "closed"]
    # The page's key has "Groomed" as a trail's third state: such a trail is open and groomed.
    assert trails[2] == {"Name": "Broadway", "Status": "Open", "StatusEnglish": "open", "Difficulty": None,
                         "Grooming": "Yes"}
    assert "Grooming" not in trails[0]


def test_a_lift_s_other_status_is_carried_in_the_page_s_words():
    lift = fortyninenorth.parse(lifts_page(CLOSED, "Wind Hold\n</span></h4>", 1), NOW)["MountainAreas"][0]["Lifts"][0]
    assert (lift["Name"], lift["Status"], lift["StatusEnglish"]) == ("Northern Spirit #1", "Wind hold", "wind hold")


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="list of lifts and trails was not found"):
        fortyninenorth.parse(lifts_page(">Lifts</h3>", ">Chairs</h3>"), NOW)
    with pytest.raises(ValueError, match="not a name, a dash and a status"):
        fortyninenorth.parse(lifts_page("<h4>Payday #3 -", "<h4>Payday #3"), NOW)
    with pytest.raises(ValueError, match="each part of the mountain once"):
        fortyninenorth.parse(lifts_page(">West Basin</h3>", ">Central Basin</h3>"), NOW)
    with pytest.raises(ValueError, match="lists a lift twice"):
        fortyninenorth.parse(lifts_page("<h4>Payday #3 -", "<h4>Silver Lode #4 -"), NOW)
    with pytest.raises(ValueError):
        fortyninenorth.parse({**PAGES, "lifts": "<html><body>Not the page</body></html>"}, NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = fortyninenorth.parse(snow_page('<h3>4"</h3>', "<h3>some</h3>", 1), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 6
    assert "SnowReport" not in fortyninenorth.parse(snow_page("Last updated:", "Posted:"), NOW)
    assert "SnowReport" not in fortyninenorth.parse(snow_page("<h3>Summit</h3>", "<h3>Peak</h3>", 1), NOW)
    assert "SnowReport" not in fortyninenorth.parse(snow_page("<h4>24 Hours</h4>", "<h4>Day</h4>"), NOW)
