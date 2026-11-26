from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import wolfcreek

# The page as the site gave it on 2026-11-26, but for the patroller's and the office reporter's names, which are
# taken out.
PAGE = (Path(__file__).parent / "fixtures" / "wolfcreek.html").read_text()
NOW = datetime(2026, 11, 26, 14, 0, tzinfo=timezone.utc)


def page(old: str, new: str) -> str:
    assert old in PAGE
    return PAGE.replace(old, new, 1)


def test_the_patrol_s_report_gives_the_two_stakes_the_snowfall_and_when_it_was_updated():
    feed = wolfcreek.parse(PAGE, NOW)
    assert feed["Name"] == "Wolf Creek" and feed["LastUpdate"] == "2026-11-26T14:00:00Z"
    snow = feed["SnowReport"]
    # "Updated: Nov 25, 2026 - 06:11", seven hours behind UTC in November.
    assert snow["LastUpdate"] == "2026-11-25T13:11:00Z" and snow["Resortwide"] is False
    assert snow["BaseArea"] == {"Name": "Midway", "BaseIn": 39, "Last24HoursIn": 0, "Last48HoursIn": 6,
                                "Last72HoursIn": 6, "Last7DaysIn": 14}
    assert snow["SummitArea"] == {"Name": "Summit", "BaseIn": 43}
    assert snow["SeasonTotalIn"] == 72 and snow["StormTotalIn"] == 6
    assert snow["BaseConditions"].startswith("Powder/Packed powder")


def test_the_site_names_no_lifts_so_only_their_count_is_carried():
    feed = wolfcreek.parse(PAGE, NOW)
    assert feed["MountainAreas"] == []
    assert feed["SnowReport"]["TotalOpenLifts"] == 10 and feed["SnowReport"]["OpenTerrainPercent"] == 100
    unsaid = wolfcreek.parse(page('data-id="span-4449-29663">10</span>', 'data-id="span-4449-29663">all</span>'), NOW)
    assert unsaid["SnowReport"]["TotalOpenLifts"] is None


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="snow report was not found"):
        wolfcreek.parse(page('class="ct-div-block snow-report-parent"', 'class="ct-div-block report"'), NOW)
    with pytest.raises(ValueError, match="does not say when it was updated"):
        wolfcreek.parse(page("Nov 25, 2026 - 06:11", "yesterday morning"), NOW)
    with pytest.raises(ValueError, match="date could not be read"):
        wolfcreek.parse(page("Nov 25, 2026 - 06:11", "Nov 31, 2026 - 06:11"), NOW)
    with pytest.raises(ValueError, match="no midway or summit depth"):
        wolfcreek.parse(page("Midway Snow Depth", "Midway"), NOW)
    with pytest.raises(ValueError, match="Summit Snow Depth reads '43 cm', not inches"):
        wolfcreek.parse(page('data-id="span-4435-29663">43</span>"', 'data-id="span-4435-29663">43</span> cm'), NOW)
    with pytest.raises(ValueError, match="gives 48 hours twice"):
        wolfcreek.parse(page(">72 hours<", ">48 hours<"), NOW)
    with pytest.raises(ValueError, match="snow report was not found"):
        wolfcreek.parse("<html><body>Just a moment...</body></html>", NOW)
