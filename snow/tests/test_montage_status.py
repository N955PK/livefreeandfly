from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import montage

# The page from its trail conditions down to its footer, with its scripts, styles and comments taken out; the reader
# gives the same on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "montage.html").read_text()
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)
CLOSED = "<td class='tg-s6z2'>Closed</td><td class='tg-s6z2'></td>"


def after(name: str, old: str, new: str, page: str = PAGE) -> str:
    """The page with the first ``old`` after the row named ``name`` replaced by ``new``."""
    at = page.index(f"<td class='tg-db0a'>{name}</td>")
    assert old in page[at:]
    return page[:at] + page[at:].replace(old, new, 1)


def changed(old: str, new: str) -> str:
    assert old in PAGE
    return PAGE.replace(old, new)


def test_the_closed_mountain_reads_its_lifts_and_trails_from_the_one_table():
    # Montage Mountain's page on 2026-11-26, before its season: eight lifts and 28 trails, all closed.
    feed = montage.parse(PAGE, NOW)
    assert feed["Name"] == "Montage Mountain" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    assert "SnowReport" not in feed
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Montage Mountain", 8, 28)]
    lifts, trails = feed["MountainAreas"][0]["Lifts"], feed["MountainAreas"][0]["Trails"]
    assert [lift["Name"] for lift in lifts] == [
        "Phoebe Snow", "The Yard – Rope Tow", "Learning Area (Magic Carpet)", "Magic Carpet", "Short Haul",
        "Iron Horse", "Long Haul", "Shuttle"]
    assert lifts[0] == {"Name": "Phoebe Snow", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}
    assert {row["StatusEnglish"] for row in lifts + trails} == {"closed"}
    by_name = {trail["Name"]: trail for trail in trails}
    assert len(by_name) == 28
    assert by_name["Easy Street"] == {"Name": "Easy Street", "Status": "Closed", "StatusEnglish": "closed",
                                      "Difficulty": "Green", "Grooming": "No"}
    # A glade has no difficulty picture, and "Doc&#8217;s Way" is read with its apostrophe.
    assert by_name["Snake (Gladed/Natural Trail)"]["Difficulty"] == ""
    assert (by_name["Doc’s Way"]["Difficulty"], by_name["Rattler"]["Difficulty"]) == ("Blue", "Black")
    assert by_name["White Lightning"]["Difficulty"] == "Double black"
    assert [sum(trail["Difficulty"] == level for trail in trails)
            for level in ("", "Green", "Blue", "Black", "Double black")] == [1, 5, 14, 5, 3]


def test_an_open_lift_and_a_groomed_open_trail_are_read_in_the_page_s_words():
    page = after("Iron Horse", "<td class='tg-s6z2'>Closed</td>", "<td class='tg-s6z2'>Open</td>")
    page = after("Mainline", CLOSED, "<td class='tg-s6z2'>OPEN</td><td class='tg-s6z2'>Yes</td>", page)
    page = after("Long Haul", "<td class='tg-s6z2'>Closed</td>", "<td class='tg-s6z2'>On Hold</td>", page)
    area = montage.parse(page, NOW)["MountainAreas"][0]
    assert [(lift["Name"], lift["Status"], lift["StatusEnglish"]) for lift in area["Lifts"]
            if lift["StatusEnglish"] != "closed"] == [("Iron Horse", "Open", "open"),
                                                      ("Long Haul", "On hold", "on hold")]
    assert [trail for trail in area["Trails"] if trail["StatusEnglish"] == "open"] == [
        {"Name": "Mainline", "Status": "Open", "StatusEnglish": "open", "Difficulty": "Green", "Grooming": "Yes"}]
    assert sum(trail["Grooming"] == "Yes" for trail in area["Trails"]) == 1


def test_a_groomed_column_the_reader_does_not_know_leaves_grooming_off(capsys):
    page = after("Mainline", CLOSED, "<td class='tg-s6z2'>Open</td><td class='tg-s6z2'>Overnight</td>")
    area = montage.parse(page, NOW)["MountainAreas"][0]
    assert len(area["Lifts"]) == 8 and len(area["Trails"]) == 28
    assert not any("Grooming" in trail for trail in area["Trails"])
    assert "['overnight']" in capsys.readouterr().out


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="0 trail status tables"):
        montage.parse(changed('id="tgtable"', 'id="status"'), NOW)
    with pytest.raises(ValueError, match="heading the reader does not know"):
        montage.parse(changed(">LIFT</th>", ">LIFTS OPEN</th>"), NOW)
    # The table cut off at its heading for the lifts lists trails alone.
    lift_heading = PAGE.index("<tr>", PAGE.index("White Lightning"))
    with pytest.raises(ValueError, match="no lifts or no trails"):
        montage.parse(PAGE[:lift_heading] + PAGE[PAGE.index("</table>"):], NOW)
    with pytest.raises(ValueError, match="difficulty picture the reader does not know"):
        montage.parse(changed("/DoubleDiamond.png", "/Glades.png"), NOW)
    with pytest.raises(ValueError, match="not a name and a status"):
        montage.parse(after("Shuttle", "<td class='tg-s6z2'>Closed</td>", "<td class='tg-s6z2'></td>"), NOW)
    with pytest.raises(ValueError, match="not a picture, a name, a status and a grooming"):
        montage.parse(after("Shuttle", CLOSED, "<td class='tg-s6z2'>Closed</td>"), NOW)
    with pytest.raises(ValueError, match="twice"):
        montage.parse(changed("<td class='tg-db0a'>Long Haul</td>", "<td class='tg-db0a'>Iron Horse</td>"), NOW)
    first = PAGE.index("<tr>")
    with pytest.raises(ValueError, match="before its first heading"):
        montage.parse(PAGE[:first] + PAGE[PAGE.index("<tr>", first + 1):], NOW)
