from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import dollar, sunvalley

# Sun Valley's page, which holds both mountains, with its scripts, styles and drawings taken out.
PAGE = (Path(__file__).parent / "fixtures" / "sunvalley.html").read_text()
NOW = datetime(2026, 11, 26, 14, 0, tzinfo=timezone.utc)
DOLLAR_LIFTS = PAGE.index('<div class="mc__tab js-mc__tab -active" data-tab="lifts-dollar">')


def changed(old: str, new: str, start: int = DOLLAR_LIFTS) -> str:
    assert old in PAGE[start:]
    return PAGE[:start] + PAGE[start:].replace(old, new, 1)


def test_dollar_mountain_is_read_from_sun_valley_s_page():
    assert dollar.URL == sunvalley.URL == "https://www.sunvalley.com/the-mountain/mountain-report"


def test_the_closed_mountain_reads_its_own_lifts_and_trails_as_closed():
    # Sun Valley's page on 2026-11-26, before Dollar Mountain opened: five lifts and 22 trails, all closed.
    feed = dollar.parse(PAGE, NOW)
    assert feed["Name"] == "Dollar Mountain" and feed["LastUpdate"] == "2026-11-26T14:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Dollar Mountain", 5, 15), ("Terrain Park", 0, 7)]
    lifts = feed["MountainAreas"][0]["Lifts"]
    # Elkhorn's row gives no hours, and the Accelerator is a rope tow.
    assert [lift["Name"] for lift in lifts] == ["Dollar", "Quarter Dollar", "Elkhorn", "Half Dollar", "The Accelerator"]
    assert lifts[0] == {"Name": "Dollar", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    # The page counts 22 trails, the seven terrain parks among them.
    assert len(trails) == 22 == len({trail["Name"] for trail in trails})
    assert {row["StatusEnglish"] for row in lifts + trails} == {"closed"}
    assert trails[0] == {"Name": "Arrowhead Way", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": "Green",
                         "Grooming": "No"}
    count = {}
    for trail in trails:
        count[trail["Difficulty"]] = count.get(trail["Difficulty"], 0) + 1
    assert count == {"Green": 8, "Blue": 5, "Black": 2, "": 7}
    # Bald Mountain's lifts and trails are not Dollar Mountain's.
    assert "Challenger" not in {lift["Name"] for lift in lifts}
    assert "Roundhouse Lane" not in {trail["Name"] for trail in trails}


def test_the_snow_report_gives_dollar_mountain_s_snowfall_and_no_depth():
    snow = dollar.parse(PAGE, NOW)["SnowReport"]
    assert snow["LastUpdate"] == "2026-11-26T12:32:00Z" and snow["Resortwide"] is True
    # Dollar Mountain's tab of the snow report has no base depth.
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": None, "OvernightIn": 0, "Last24HoursIn": 0,
                                "Last7DaysIn": 0}
    assert snow["SeasonTotalIn"] == 0 and snow["BaseConditions"] is None


def test_an_open_lift_and_a_groomed_open_trail_take_the_words_of_the_page_s_key():
    closed = '<span class="mc__icon mc__icon-closed"></span>'
    lift = closed + '\n <span class="sr-only">Lift Closed</span>'
    feed = dollar.parse(changed(lift, '<span class="mc__icon mc__icon-open"></span>'), NOW)
    assert feed["MountainAreas"][0]["Lifts"][0] == {"Name": "Dollar", "Status": "Open", "StatusEnglish": "open",
                                                    "Difficulty": None}
    trails = PAGE.index('<div class="mc__tab js-mc__tab -active" data-tab="trails-dollar">')
    row = (closed + '\n <span class="sr-only">Trail Closed</span>\n </td>\n'
           ' <td class="mc__table-cell mc__table-cell-svg">\n')
    groomed = ('<span class="mc__icon mc__icon-open"></span>\n </td>\n <td class="mc__table-cell mc__table-cell-svg">\n'
               ' <span class="mc__icon mc__icon-groomed"></span>\n')
    feed = dollar.parse(changed(row, groomed, trails), NOW)
    assert feed["MountainAreas"][0]["Trails"][0] == {"Name": "Arrowhead Way", "Status": "Open", "StatusEnglish": "open",
                                                     "Difficulty": "Green", "Grooming": "Yes"}


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="0 lifts tabs for dollar"):
        dollar.parse(PAGE.replace('data-tab="lifts-dollar">', 'data-tab="lifts-elkhorn">'), NOW)
    with pytest.raises(ValueError, match="counts 6 lifts but 5"):
        dollar.parse(changed('<span class="mc-lifts__graph-value">0 / 5</span>',
                             '<span class="mc-lifts__graph-value">0 / 6</span>'), NOW)
    with pytest.raises(ValueError, match="counts 23 trails but 22"):
        dollar.parse(changed('<span class="mc-lifts__graph-value">0 / 22</span>',
                             '<span class="mc-lifts__graph-value">0 / 23</span>'), NOW)
    with pytest.raises(ValueError, match="Dollar has status symbols \\['shut'\\]"):
        dollar.parse(changed('<span class="mc__icon mc__icon-closed"></span>\n <span class="sr-only">Lift Closed',
                             '<span class="mc__icon mc__icon-shut"></span>\n <span class="sr-only">Lift Closed'), NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = dollar.parse(PAGE.replace('data-tab="weather-dollar">', 'data-tab="snow-dollar">'), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 2
