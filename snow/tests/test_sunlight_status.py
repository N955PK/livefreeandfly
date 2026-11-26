from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import sunlight

# The page's current status and trail status with its scripts, styles, menus and layout settings taken out; the
# reader gives the same on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "sunlight.html").read_text()
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)
BOX = '</span> </span><p class="elementor-icon-box-description"> '


def changed(old: str, new: str, count: int = -1) -> str:
    assert old in PAGE
    return PAGE.replace(old, new, count)


def test_the_preseason_mountain_reads_its_lifts_and_trails():
    # Sunlight's page on 2026-11-26, before its December 11 opening: three lifts and 75 trails, all closed.
    feed = sunlight.parse(PAGE, NOW)
    assert feed["Name"] == "Sunlight" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    assert [area["Name"] for area in feed["MountainAreas"]] == ["Sunlight"]
    area = feed["MountainAreas"][0]
    assert area["Lifts"] == [
        {"Name": "Primo Chair", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None},
        {"Name": "Segundo Chair", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None},
        {"Name": "Tercero Chair", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}]
    trails = {trail["Name"]: trail for trail in area["Trails"]}
    # The page counts 77 trails: its two uphill routes are left out.
    assert len(trails) == 75 and {trail["StatusEnglish"] for trail in trails.values()} == {"closed"}
    assert trails["Buckmaster"] == {"Name": "Buckmaster", "Status": "Closed", "StatusEnglish": "closed",
                                    "Difficulty": "Green", "Grooming": "No"}
    assert trails["Ivy's Run"]["Difficulty"] == "Green" and trails["Beaujolais"]["Difficulty"] == "Blue"
    # A trail the page gives no grooming for ("UNDEF") carries none, and a park has no difficulty.
    assert trails["Blue Finger"] == {"Name": "Blue Finger", "Status": "Closed", "StatusEnglish": "closed",
                                     "Difficulty": "Black"}
    assert trails["Sherick Park"]["Difficulty"] == "" and trails["Sherick Park"]["Grooming"] == "Yes"
    assert [sum(trail["Difficulty"] == level for trail in trails.values())
            for level in ("Green", "Blue", "Black", "Double black", "")] == [11, 22, 13, 28, 1]


def test_the_snow_report_is_read_without_a_date():
    snow = sunlight.parse(PAGE, NOW)["SnowReport"]
    assert snow == {"LastUpdate": None, "Resortwide": True, "BaseConditions": "Low snowfall", "SeasonTotalIn": 0,
                    "BaseArea": {"Name": "Mountain", "SinceLiftsClosedIn": 0, "Last24HoursIn": 0,
                                 "Last48HoursIn": 0, "BaseIn": 0}, "Report": None, "Alert": None}
    page = changed(f"Base Depth {BOX}0&quot;", f"Base Depth {BOX}34.5&quot;")
    page = page.replace(f"Last 24 Hours {BOX}0&quot;", f"Last 24 Hours {BOX}6&quot;")
    page = page.replace(f"Season Total {BOX}0&quot;", f"Season Total {BOX}112&quot;")
    page = page.replace(f"Primary Surface {BOX}LOW_SNOWFALL", f"Primary Surface {BOX}PACKED_POWDER")
    snow = sunlight.parse(page, NOW)["SnowReport"]
    assert snow["BaseArea"]["BaseIn"] == 34.5 and snow["BaseArea"]["Last24HoursIn"] == 6
    assert snow["SeasonTotalIn"] == 112 and snow["BaseConditions"] == "Packed powder"


def test_an_open_lift_and_an_open_trail_are_read():
    page = changed('Primo Chair</span><span class="condens_bld sz24">CLOSED', 'Primo Chair</span><span '
                   'class="condens_bld sz24">OPEN')
    page = page.replace('<div class="trl_opn closed"> CLOSED</div>', '<div class="trl_opn open"> OPEN</div>', 1)
    area = sunlight.parse(page, NOW)["MountainAreas"][0]
    assert area["Lifts"][0] == {"Name": "Primo Chair", "Status": "Open", "StatusEnglish": "open", "Difficulty": None}
    assert area["Lifts"][1]["StatusEnglish"] == "closed"
    assert area["Trails"][0]["StatusEnglish"] == "open" and area["Trails"][1]["StatusEnglish"] == "closed"
    hold = changed('Primo Chair</span><span class="condens_bld sz24">CLOSED', 'Primo Chair</span><span '
                   'class="condens_bld sz24">WIND HOLD')
    lift = sunlight.parse(hold, NOW)["MountainAreas"][0]["Lifts"][0]
    assert (lift["Status"], lift["StatusEnglish"]) == ("Wind hold", "wind hold")


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="current status and its list of lifts were not found"):
        sunlight.parse(changed(">LIFTS</h4>", ">CHAIRS</h4>"), NOW)
    with pytest.raises(ValueError, match="trail status was not found"):
        sunlight.parse(changed('<div class="trl_stuts">', '<div class="trails">'), NOW)
    with pytest.raises(ValueError, match="a difficulty the reader does not know: ORANGE_OVAL"):
        sunlight.parse(changed('data-level="BLUE_SQUARE"', 'data-level="ORANGE_OVAL"'), NOW)
    with pytest.raises(ValueError, match="grooming reads 'MAYBE'"):
        sunlight.parse(changed("<span>(GROOMED)</span>", "<span>(MAYBE)</span>"), NOW)
    with pytest.raises(ValueError, match="counts 11 trails under EASIEST but 10 were read"):
        sunlight.parse(changed('<div class="trl_opn closed">', '<div class="status">', 1), NOW)
    with pytest.raises(ValueError, match="counts 0/4 lifts but 3 were read"):
        sunlight.parse(changed(f"Open Lifts {BOX}0/3", f"Open Lifts {BOX}0/4"), NOW)
    with pytest.raises(ValueError, match="counts 0/80 trails but 77 were read"):
        sunlight.parse(changed(f"Open Trails {BOX}0/77", f"Open Trails {BOX}0/80"), NOW)
    with pytest.raises(ValueError):
        sunlight.parse("<html><body>Not the page</body></html>", NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = sunlight.parse(changed(f"Base Depth {BOX}0&quot;", f"Base Depth {BOX}deep"), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"][0]["Trails"]) == 75
    assert "SnowReport" not in sunlight.parse(changed(f"Last 24 Hours {BOX}", f"Yesterday {BOX}"), NOW)
