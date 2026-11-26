from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import castlemountain

# The page's report (from its main content to its webcams) with its scripts, styles and comments taken out, and a
# line end put after each table row; the reader gives the same on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "castlemountain.html").read_text()
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)
ICONS = "https://www.skicastle.ca/wp-content/plugins/castle-mountain-live/icons"
CLOSED = f'<img decoding="async" src="{ICONS}/Closed.svg" alt="Closed" title="Closed">'
NOT_GROOMED = f'<img decoding="async" src="{ICONS}/D-ND.svg" alt="" width="45"> Not Groomed'


def changed(old: str, new: str, count: int = -1) -> str:
    assert old in PAGE
    return PAGE.replace(old, new, count)


def symbol(name: str) -> str:
    return f'<img decoding="async" src="{ICONS}/{name}.svg" alt="{name}" title="{name}">'


def test_the_preseason_mountain_reads_its_lifts_and_each_zone_s_trails():
    # Castle Mountain's page on 2026-11-26, before opening: seven lifts and 119 trails, all closed.
    feed = castlemountain.parse(PAGE, NOW)
    assert feed["Name"] == "Castle Mountain" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Lifts", 7, 0), ("Chutes Far Chutes", 0, 15), ("Green Chair", 0, 3), ("Huckleberry Chair", 0, 14),
        ("Stagecoach Express", 0, 20), ("Sundance Blue Chair", 0, 28), ("Tamarack Red Chair", 0, 39)]
    lifts = feed["MountainAreas"][0]["Lifts"]
    assert [lift["Name"] for lift in lifts] == [
        "Green Chair", "Buckaroo Carpet", "Huckleberry Chair", "Stagecoach Express Chair", "Sundance (Blue) Chair",
        "T-Rex", "Tamarack (Red) Chair"]
    assert lifts[0] == {"Name": "Green Chair", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    assert len(trails) == 119 and {trail["StatusEnglish"] for trail in trails} == {"closed"}
    assert trails[0] == {"Name": "Cinch Fork", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": "Green",
                         "Grooming": "No"}
    by_name = {trail["Name"]: trail for trail in trails}
    assert by_name["Cinch Traverse"]["Difficulty"] == "Blue" and by_name["Blazing Saddle"]["Difficulty"] == "Black"
    assert by_name["Desperado"]["Difficulty"] == "Double black"
    # A terrain park has no difficulty.
    assert by_name["Tumbleweed Terrain Park"]["Difficulty"] == ""
    assert sorted({trail["Difficulty"] for trail in trails}) == ["", "Black", "Blue", "Double black", "Green"]


def test_the_snow_report_gives_mid_mountain_in_inches_and_when_it_was_updated():
    snow = castlemountain.parse(PAGE, NOW)["SnowReport"]
    # "Last updated: 2026-11-21 - 06:05 MT", Alberta's time; 21 cm in 7 days is 8.3 inches and the season's 40 cm
    # is 15.7.
    updated = datetime(2026, 11, 21, 6, 5, tzinfo=castlemountain.MOUNTAIN_TIME).astimezone(timezone.utc)
    assert snow["LastUpdate"] == updated.strftime("%Y-%m-%dT%H:%M:%SZ") and snow["Resortwide"] is True
    assert snow["MidMountainArea"] == {"Name": "Mid Mountain", "Last12HoursIn": 0.0, "Last24HoursIn": 0.0,
                                       "Last48HoursIn": 0.0, "Last72HoursIn": 0.0, "Last7DaysIn": 8.3, "BaseIn": 0.0}
    assert snow["SeasonTotalIn"] == 15.7 and snow["BaseConditions"] is None
    deep = castlemountain.parse(changed("<tr><td>Snow Base</td><td>0</td></tr>",
                                        "<tr><td>Snow Base</td><td>142</td></tr>"), NOW)["SnowReport"]
    assert deep["MidMountainArea"]["BaseIn"] == 55.9


def test_an_open_lift_and_a_groomed_open_trail_are_read():
    page = changed(f"<td>Green Chair</td><td>{CLOSED}</td>", f"<td>Green Chair</td><td>{symbol('Open')}</td>")
    page = page.replace(f"<td>Cinch Fork</td><td>{CLOSED}</td><td>{NOT_GROOMED}</td>",
                        f"<td>Cinch Fork</td><td>{symbol('Open')}</td><td>"
                        f'<img decoding="async" src="{ICONS}/D-G.svg" alt="" width="45"> Groomed</td>')
    page = page.replace("<strong>0</strong> of 7 lifts open", "<strong>1</strong> of 7 lifts open")
    page = page.replace("<strong>0</strong> of 119 trails open", "<strong>1</strong> of 119 trails open")
    feed = castlemountain.parse(page, NOW)
    assert feed["MountainAreas"][0]["Lifts"][0] == {"Name": "Green Chair", "Status": "Open", "StatusEnglish": "open",
                                                    "Difficulty": None}
    assert feed["MountainAreas"][1]["Trails"][0] == {"Name": "Cinch Fork", "Status": "Open", "StatusEnglish": "open",
                                                     "Difficulty": "Green", "Grooming": "Yes"}
    assert feed["MountainAreas"][1]["Trails"][1]["StatusEnglish"] == "closed"


def test_the_key_s_other_statuses_are_carried():
    page = changed(f"<td>T-Rex</td><td>{CLOSED}</td>", f"<td>T-Rex</td><td>{symbol('On Hold')}</td>")
    page = page.replace(f"<td>Buckaroo Carpet</td><td>{CLOSED}</td>",
                        f"<td>Buckaroo Carpet</td><td>{symbol('Expected')}</td>")
    lifts = {lift["Name"]: lift for lift in castlemountain.parse(page, NOW)["MountainAreas"][0]["Lifts"]}
    assert (lifts["T-Rex"]["Status"], lifts["T-Rex"]["StatusEnglish"]) == ("On hold", "on hold")
    assert lifts["Buckaroo Carpet"]["StatusEnglish"] == "expected"


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="lift table was not found"):
        castlemountain.parse(changed('class="cml-table cml-lifts"', 'class="lifts"'), NOW)
    with pytest.raises(ValueError, match="T-Rex has the status 'Shut'"):
        castlemountain.parse(changed(f"<td>T-Rex</td><td>{CLOSED}</td>", f"<td>T-Rex</td><td>{symbol('Shut')}</td>"),
                             NOW)
    with pytest.raises(ValueError, match="difficulty symbol the reader does not know: 'orange oval'"):
        castlemountain.parse(changed('alt="terrain parks"', 'alt="orange oval"', 1), NOW)
    with pytest.raises(ValueError, match="grooming reads 'maybe'"):
        castlemountain.parse(changed(f"{NOT_GROOMED}</td>", "Maybe</td>", 1), NOW)
    with pytest.raises(ValueError, match="not rows of 4 cells"):
        castlemountain.parse(changed("<td>Closed for the season</td>", "", 1), NOW)
    # An open lift the page's own count does not have, and a trail table that is not read.
    with pytest.raises(ValueError, match="counts 0 of 7 lifts open but 1 of 7 were read"):
        castlemountain.parse(changed(f"<td>T-Rex</td><td>{CLOSED}</td>", f"<td>T-Rex</td><td>{symbol('Open')}</td>"),
                             NOW)
    with pytest.raises(ValueError, match="counts 0 of 119 trails open but 0 of 118 were read"):
        castlemountain.parse(changed(f"<tr><td><img decoding=\"async\" src=\"{ICONS}/blue_square.svg\" "
                                     f"alt=\"blue square\" width=\"25\"></td><td>Cinch Traverse</td><td>{CLOSED}</td>"
                                     f"<td>{NOT_GROOMED}</td></tr>", ""), NOW)
    with pytest.raises(ValueError, match="6 trail tables but 5 were read"):
        castlemountain.parse(changed('<div class="cml-zone-list" id="cml-green-chair" hidden>',
                                     '<div class="zone" id="cml-green-chair" hidden>'), NOW)
    with pytest.raises(ValueError, match="no name or is listed twice"):
        castlemountain.parse(changed('<option value="cml-green-chair">', '<option value="green-chair">'), NOW)
    with pytest.raises(ValueError):
        castlemountain.parse("<html><body>Not the page</body></html>", NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = castlemountain.parse(changed("<tr><td>Snow Base</td><td>0</td></tr>",
                                        "<tr><td>Snow Base</td><td>deep</td></tr>"), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 7
    assert "SnowReport" not in castlemountain.parse(changed("Last updated: 2026-11-21", "Last updated: Saturday"), NOW)
    assert "SnowReport" not in castlemountain.parse(changed("Snow Fall (cm)", "Snow Fall (in)"), NOW)
    assert "SnowReport" not in castlemountain.parse(changed("<tr><td>Snow Base</td><td>0</td></tr>", ""), NOW)
