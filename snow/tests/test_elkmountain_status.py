import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import elkmountain

# The page with its scripts, styles, drawings, header and footer taken out; the reader gives the same on the whole
# page.
PAGE = (Path(__file__).parent / "fixtures" / "elkmountain.html").read_text()
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)
CLOSED = '<span class="elk-snow-badge elk-snow-closed">Closed</span></td>'
DEPTH = '<span class="elk-snow-tile-value">{}</span><span class="elk-snow-tile-label">Base depth</span>'


def changed(old: str, new: str, count: int = -1, page: str = PAGE) -> str:
    assert old in page
    return page.replace(old, new, count)


def after(page: str, name: str, old: str, new: str) -> str:
    """The page with the first ``old`` after the row named ``name`` replaced by ``new``."""
    at = page.index(f'<th scope="row">{name}')
    assert old in page[at:]
    return page[:at] + page[at:].replace(old, new, 1)


def test_the_closed_mountain_reads_its_lifts_and_the_trails_of_each_table():
    # Elk Mountain's page on 2026-11-26, last updated when it closed in March: seven lifts, 27 trails and two
    # parks, all closed.
    feed = elkmountain.parse(PAGE, NOW)
    assert feed["Name"] == "Elk Mountain" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Elk Mountain", 7, 0), ("Easy", 0, 6), ("Intermediate", 0, 10), ("Expert", 0, 11), ("Terrain Parks", 0, 2)]
    lifts = feed["MountainAreas"][0]["Lifts"]
    assert lifts[0] == {"Name": "Beginners Chair (Double) A", "Status": "Closed", "StatusEnglish": "closed",
                        "Difficulty": None}
    assert lifts[-1]["Name"] == "Cable Tow in Stompin' Grounds Terrain Park"
    trails = {trail["Name"]: trail for area in feed["MountainAreas"] for trail in area["Trails"]}
    assert len(trails) == 29 and {trail["StatusEnglish"] for trail in trails.values()} == {"closed"}
    # A trail's name is read without the note of snowmaking and grooming set after it for narrow screens.
    assert trails["Lehigh"] == {"Name": "Lehigh", "Status": "Closed", "StatusEnglish": "closed",
                                "Difficulty": "Green", "Grooming": "No"}
    assert (trails["Delaware/Delaware Chute"]["Difficulty"], trails["Mohawk"]["Difficulty"]) == ("Blue", "Black")
    assert trails["Little Foot Progression Park"]["Difficulty"] == ""


def test_the_conditions_report_gives_when_it_was_updated_and_no_depth_out_of_season():
    snow = elkmountain.parse(PAGE, NOW)["SnowReport"]
    # "Updated March 23, 2026 9:55 am", in Eastern time.
    assert snow["LastUpdate"] == "2026-03-23T13:55:00Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": None, "Last24HoursIn": 0}
    assert snow["BaseConditions"] is None and snow["SeasonTotalIn"] is None


def test_in_season_the_base_depth_is_one_depth_or_a_least_and_a_most_and_the_surface_is_read():
    page = re.sub(r"(<th scope=\"row\">Surface conditions</th>\s*<td>)&ndash;(</td>)", r"\1Machine groomed\2", PAGE)
    snow = elkmountain.parse(changed(DEPTH.format("&ndash;"), DEPTH.format('36"'), page=page), NOW)["SnowReport"]
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": 36, "Last24HoursIn": 0}
    assert snow["BaseConditions"] == "Machine groomed"
    spread = elkmountain.parse(changed(DEPTH.format("&ndash;"), DEPTH.format("24 &ndash; 48")), NOW)["SnowReport"]
    assert spread["BaseArea"] == {"Name": "Mountain", "BaseMinIn": 24, "BaseMaxIn": 48, "Last24HoursIn": 0}


def test_open_and_partly_open_rows_and_a_groomed_trail_are_read():
    page = after(PAGE, "East Chair (Double) B", CLOSED, CLOSED.replace("closed", "open").replace("Closed", "Open"))
    page = after(page, "Lehigh", CLOSED, CLOSED.replace("closed", "open").replace("Closed", "Open"))
    page = after(page, "Lehigh", '<td data-label="Groomed"><span class="elk-snow-no">No</span></td>',
                 '<td data-label="Groomed"><span class="elk-snow-yes">Yes</span></td>')
    page = after(page, "Tioga", CLOSED, '<span class="elk-snow-badge elk-snow-partial">Partially'
                                        '<span class="elk-snow-long"> open</span></span></td>')
    areas = elkmountain.parse(page, NOW)["MountainAreas"]
    assert [lift["StatusEnglish"] for lift in areas[0]["Lifts"][:3]] == ["closed", "open", "closed"]
    assert areas[1]["Trails"][0] == {"Name": "Lehigh", "Status": "Open", "StatusEnglish": "open",
                                     "Difficulty": "Green", "Grooming": "Yes"}
    assert areas[1]["Trails"][1] == {"Name": "Tioga", "Status": "Partially open",
                                     "StatusEnglish": "partially open", "Difficulty": "Green", "Grooming": "No"}


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="Lehigh is marked shut but reads 'Closed'"):
        elkmountain.parse(after(PAGE, "Lehigh", CLOSED, CLOSED.replace("elk-snow-closed", "elk-snow-shut")), NOW)
    with pytest.raises(ValueError, match="a table the reader does not know: glades"):
        elkmountain.parse(changed("elk-snow-group elk-snow-group-expert", "elk-snow-group elk-snow-group-glades"), NOW)
    with pytest.raises(ValueError, match="Lehigh does not say whether it is groomed"):
        elkmountain.parse(after(PAGE, "Lehigh", '<td data-label="Groomed">', '<td data-label="Night">'), NOW)
    with pytest.raises(ValueError, match="not a name and a status in a badge"):
        elkmountain.parse(after(PAGE, "Lehigh", CLOSED, "Closed</td>"), NOW)
    with pytest.raises(ValueError, match="counts 8 under 'lifts open' but 7 were read"):
        elkmountain.parse(changed("0<small> / 7</small>", "0<small> / 8</small>"), NOW)
    with pytest.raises(ValueError, match="counts 27 under 'trails open' but 26 were read"):
        elkmountain.parse(re.sub(r"<tr>\s*<th scope=\"row\">Lehigh.*?</tr>", "", PAGE, flags=re.S), NOW)
    with pytest.raises(ValueError, match="no lifts or no trails"):
        elkmountain.parse("<html><body>Not the page</body></html>", NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = elkmountain.parse(changed(DEPTH.format("&ndash;"), DEPTH.format("deep")), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"][0]["Lifts"]) == 7
    assert "SnowReport" not in elkmountain.parse(changed("Updated March 23, 2026 9:55 am", "Updated today"), NOW)
    assert "SnowReport" not in elkmountain.parse(changed(">Base depth<", ">Snow stake<"), NOW)
