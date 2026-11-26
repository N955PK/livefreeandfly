from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import horseshoe

# The page's report (its date, weather, Alpine, Chair Lifts, Nordic and tube park parts) with its scripts, styles
# and blank lines taken out; the reader gives the same on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "horseshoe.html").read_text()
# The day the page was saved, at 1pm in Ontario, and a winter's day there at noon and at 6pm.
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)
NOON = datetime(2027, 1, 16, 17, 0, tzinfo=timezone.utc)
EVENING = datetime(2027, 1, 16, 23, 0, tzinfo=timezone.utc)
CLOSED = '<td class="closed"><span class="screen-reader-text">closed</span></td>'
OPEN = '<td class="open"><span class="screen-reader-text">open</span></td>'
NIGHT_OFF = '<td class="not-available"><span class="screen-reader-text">Not available</span></td>'


def changed(old: str, new: str, count: int = -1, page: str = PAGE) -> str:
    assert old in page
    return page.replace(old, new, count)


def row(name: str, day: str, night: str, page: str = PAGE) -> str:
    """The page with the two statuses of the row named ``name`` replaced."""
    start = page.index(f"<td>{name}</td>")
    end = page.index("</tr>", start)
    return page[:start] + f"<td>{name}</td>\n{day}\n{night}\n" + page[end:]


def winter(page: str = PAGE) -> str:
    """The page as if it had been updated on the winter's day."""
    return changed("Updated: Sunday, April 5, 2026", "Updated: Saturday, January 16, 2027", page=page)


def test_the_closed_mountain_reads_its_lifts_and_each_difficulty_s_runs():
    # Horseshoe Valley's page on 2026-11-26, closed for the season: six lifts and 27 runs, all closed.
    feed = horseshoe.parse(PAGE, NOW)
    assert feed["Name"] == "Horseshoe Valley" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Lifts", 6, 0), ("Easy", 0, 8), ("Difficult", 0, 15), ("More Difficult", 0, 2), ("Terrain Park", 0, 2)]
    lifts = feed["MountainAreas"][0]["Lifts"]
    assert [lift["Name"] for lift in lifts] == [
        "Kimbles Carpet", "Snow School Express", "Double Chair", "Copeland Express 6 Person Chair",
        "High Rider Quad", "Highland Express Quad"]
    assert lifts[0] == {"Name": "Kimbles Carpet", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}
    trails = {trail["Name"]: trail for area in feed["MountainAreas"] for trail in area["Trails"]}
    assert len(trails) == 27 and {trail["StatusEnglish"] for trail in trails.values()} == {"closed"}
    assert trails["Ponyback"] == {"Name": "Ponyback", "Status": "Closed", "StatusEnglish": "closed",
                                  "Difficulty": "Green"}
    assert trails["Steeplechase"]["Difficulty"] == "Blue" and trails["Race Hill"]["Difficulty"] == "Black"
    # The terrain park's runs have no difficulty, and the cross-country trails (5, 9, 6 ...) are not read.
    assert trails["Bullpen"]["Difficulty"] == "" and "5" not in trails


def test_a_row_reads_the_day_s_status_until_the_day_ends_and_then_the_night_s():
    page = winter(row("Ponyback", OPEN, CLOSED))
    page = row("The Zipper", OPEN, NIGHT_OFF, page)
    page = row("Pinto", CLOSED, OPEN, page)
    page = row("Double Chair", OPEN, CLOSED, page)
    page = row("High Rider Quad", OPEN, OPEN, page)

    def read(now):
        feed = horseshoe.parse(page, now)
        return {found["Name"]: found["StatusEnglish"] for area in feed["MountainAreas"]
                for found in area["Lifts"] + area["Trails"]}

    day, night = read(NOON), read(EVENING)
    assert (day["Ponyback"], day["The Zipper"], day["Pinto"]) == ("open", "open", "closed")
    assert (day["Double Chair"], day["High Rider Quad"], day["Kimbles Carpet"]) == ("open", "open", "closed")
    # A run that is not skied at night ("Not available") reads closed then.
    assert (night["Ponyback"], night["The Zipper"], night["Pinto"]) == ("closed", "closed", "open")
    assert (night["Double Chair"], night["High Rider Quad"]) == ("closed", "open")
    # The day's column holds through the hour the two overlap (3:30pm to 4:30pm) and the night's from 4:30pm.
    assert read(datetime(2027, 1, 16, 21, 29, tzinfo=timezone.utc))["Ponyback"] == "open"
    assert read(datetime(2027, 1, 16, 21, 30, tzinfo=timezone.utc))["Ponyback"] == "closed"
    lift = horseshoe.parse(page, NOON)["MountainAreas"][0]["Lifts"][2]
    assert lift == {"Name": "Double Chair", "Status": "Open", "StatusEnglish": "open", "Difficulty": None}


def test_the_snow_report_is_the_snowfall_and_the_depth_in_inches_dated_the_day_of_the_page():
    snow = horseshoe.parse(PAGE, NOW)["SnowReport"]
    # "Updated: Sunday, April 5, 2026", the start of that day in Ontario; no depth or surface out of season.
    assert snow == {"LastUpdate": "2026-04-05T04:00:00Z", "Resortwide": True, "BaseConditions": None,
                    "SeasonTotalIn": None, "BaseArea": {"Name": "Base", "Last24HoursIn": 0.0}, "Report": None,
                    "Alert": None}
    page = changed('<span class="data">0</span><span class="unit">cm</span>',
                   '<span class="data">12</span><span class="unit">cm</span>', page=winter())
    filled = "<dt>Conditions</dt>\n              <dd>Machine Groomed</dd>\n              <dt>Base Depth</dt>\n"
    empty = "<dt>Conditions</dt>\n              <dd></dd>\n              <dt>Base Depth</dt>\n              <dd></dd>"
    one = horseshoe.parse(changed(empty, f"{filled}              <dd>60 cm</dd>", page=page), NOON)["SnowReport"]
    assert one["LastUpdate"] == "2027-01-16T05:00:00Z" and one["BaseConditions"] == "Machine Groomed"
    assert one["BaseArea"] == {"Name": "Base", "Last24HoursIn": 4.7, "BaseIn": 23.6}
    # A depth given as a low and a high is carried as both; the runner gives the middle.
    two = horseshoe.parse(changed(empty, f"{filled}              <dd>40 - 80cm</dd>", page=page), NOON)["SnowReport"]
    assert two["BaseArea"] == {"Name": "Base", "Last24HoursIn": 4.7, "BaseMinIn": 15.7, "BaseMaxIn": 31.5}


def test_last_season_s_page_with_anything_open_is_refused():
    with pytest.raises(ValueError, match="last updated 2026-04-05 and has lifts or runs open"):
        horseshoe.parse(row("Double Chair", OPEN, CLOSED), NOW)
    # The same page read within the fortnight is the mountain's last days.
    feed = horseshoe.parse(row("Double Chair", OPEN, CLOSED), datetime(2026, 4, 6, 15, 0, tzinfo=timezone.utc))
    assert feed["MountainAreas"][0]["Lifts"][2]["StatusEnglish"] == "open"


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="Alpine and the Chair Lifts parts of the report were not found"):
        horseshoe.parse(changed('class="report report-lifts"', 'class="report lifts"'), NOW)
    with pytest.raises(ValueError, match="Kimbles Carpet is marked 'hold'"):
        horseshoe.parse(row("Kimbles Carpet", '<td class="hold"><span class="screen-reader-text">hold</span></td>',
                            CLOSED), NOW)
    with pytest.raises(ValueError, match="Kimbles Carpet is marked closed but reads 'open'"):
        horseshoe.parse(row("Kimbles Carpet", '<td class="closed"><span class="screen-reader-text">open</span></td>',
                            CLOSED), NOW)
    with pytest.raises(ValueError, match="not a name and a status for the day and for the night"):
        horseshoe.parse(row("Kimbles Carpet", CLOSED, ""), NOW)
    with pytest.raises(ValueError, match="headed 'Easy' with the symbol 'purple star'"):
        horseshoe.parse(changed('alt="Green circle"', 'alt="Purple star"'), NOW)
    with pytest.raises(ValueError, match="not headed by the hours"):
        horseshoe.parse(changed("3:30pm - 9:00pm</th>", "Night</th>", 1), NOW)
    with pytest.raises(ValueError, match="does not start by the end of the day's"):
        horseshoe.parse(changed("3:30pm - 9:00pm</th>", "5:30pm - 9:00pm</th>", 1), NOW)
    with pytest.raises(ValueError, match="33 rows of lifts and runs but 31 were read"):
        horseshoe.parse(changed('<table class="report-table">', '<table class="report">', 4).replace(
            '<table class="report">', '<table class="report-table">', 3), NOW)
    with pytest.raises(ValueError, match="does not say when it was updated"):
        horseshoe.parse(changed("Updated: Sunday, April 5, 2026", "Updated this morning"), NOW)
    with pytest.raises(ValueError, match="date could not be read"):
        horseshoe.parse(changed("Updated: Sunday, April 5, 2026", "Updated: Sunday, Germinal 5, 2026"), NOW)
    with pytest.raises(ValueError):
        horseshoe.parse("<html><body>Not the page</body></html>", NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = horseshoe.parse(changed('<span class="data">0</span><span class="unit">cm</span>',
                                   '<span class="data">a dusting</span><span class="unit">cm</span>'), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 5
    assert "SnowReport" not in horseshoe.parse(changed("<dt>Base Depth</dt>\n              <dd></dd>",
                                                       "<dt>Base Depth</dt>\n              <dd>plenty</dd>"), NOW)
    assert "SnowReport" not in horseshoe.parse(changed("<dt>Base Depth</dt>\n              <dd></dd>", "", 1), NOW)
