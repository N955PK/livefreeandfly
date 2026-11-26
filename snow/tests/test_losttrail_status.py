from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import losttrail

# The page with its scripts, styles, drawings, header and footer taken out; the reader gives the same on the whole
# page.
PAGE = (Path(__file__).parent / "fixtures" / "losttrail.html").read_text()
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)
SAID = '<span class="elementor-heading-title elementor-size-default">{}</span>'


def changed(old: str, new: str, count: int = -1) -> str:
    assert old in PAGE
    return PAGE.replace(old, new, count)


def test_the_preseason_mountain_reads_its_five_chairs():
    # Lost Trail's page on 2026-11-26, before opening: five chairs, all closed, and no list of trails.
    feed = losttrail.parse(PAGE, NOW)
    assert feed["Name"] == "Lost Trail" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), area["Trails"]) for area in feed["MountainAreas"]] == [
        ("Lost Trail", 5, [])]
    lifts = feed["MountainAreas"][0]["Lifts"]
    assert [lift["Name"] for lift in lifts] == ["Chair 1", "Chair 2", "Chair 3", "Chair 4", "Chair 5"]
    assert lifts[0] == {"Name": "Chair 1", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}
    assert {lift["StatusEnglish"] for lift in lifts} == {"closed"}


def test_the_snow_report_gives_the_bottom_and_the_top_and_when_it_was_written():
    snow = losttrail.parse(PAGE, NOW)["SnowReport"]
    # "Snow Report for November 23, 2026 9:00 am", in Mountain time.
    assert snow["LastUpdate"] == "2026-11-23T16:00:00Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Bottom", "SinceLiftsClosedIn": 8, "Last24HoursIn": 2, "Last48HoursIn": 2,
                                "BaseIn": 8}
    assert snow["SummitArea"] == {"Name": "Top", "BaseIn": 10}
    assert snow["SeasonTotalIn"] == 31 and snow["BaseConditions"] == "Off-Piste"
    # The page counts its trails and does not list them.
    assert (snow["TotalOpenTrails"], snow["TotalTrails"]) == (0, 69)


def test_open_and_held_chairs_are_carried_in_the_page_s_words():
    page = changed(SAID.format("Closed"), SAID.format("Open"), 2)
    page = page.replace(SAID.format("Closed"), SAID.format("Wind Hold"), 1).replace(SAID.format("0/5"),
                                                                                  SAID.format("2/5"))
    lifts = losttrail.parse(page, NOW)["MountainAreas"][0]["Lifts"]
    assert [lift["StatusEnglish"] for lift in lifts] == ["open", "open", "wind hold", "closed", "closed"]
    assert lifts[2] == {"Name": "Chair 3", "Status": "Wind hold", "StatusEnglish": "wind hold", "Difficulty": None}


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="lift report was not found"):
        losttrail.parse(changed(">Lift Report</h2>", ">Lifts</h2>"), NOW)
    with pytest.raises(ValueError, match="counts 0 of 6 lifts open but 0 of 5 were read"):
        losttrail.parse(changed(SAID.format("0/5"), SAID.format("0/6")), NOW)
    with pytest.raises(ValueError, match="count under 'Number of Lifts Open' was not found"):
        losttrail.parse(changed(SAID.format("0/5"), SAID.format("none")), NOW)
    with pytest.raises(ValueError, match="lists no lifts"):
        losttrail.parse(changed(SAID.format("Closed"), "<p>Closed</p>"), NOW)
    with pytest.raises(ValueError):
        losttrail.parse("<html><body>Not the page</body></html>", NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = losttrail.parse(changed(SAID.format('10"'), SAID.format("deep")), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"][0]["Lifts"]) == 5
    assert "SnowReport" not in losttrail.parse(changed("Snow Report for November 23, 2026 9:00 am",
                                                       "Snow Report for this morning"), NOW)
    assert "SnowReport" not in losttrail.parse(changed("Snow Depth - Bottom", "Snow Stake"), NOW)
    assert "SnowReport" not in losttrail.parse(changed(SAID.format("0/69"), SAID.format("few")), NOW)
