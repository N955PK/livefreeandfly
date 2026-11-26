import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import windham

# The map's statuses with their scripts taken out; the reader gives the same on the whole piece.
PAGE = (Path(__file__).parent / "fixtures" / "windham.html").read_text()
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)
CLOSED = '<img src="images/icons/close.svg" />Closed'


def changed(old: str, new: str, count: int = -1) -> str:
    assert old in PAGE
    return PAGE.replace(old, new, count)


def marker(name: str, mark: str, new_mark: str, said: str) -> str:
    """The map with the marker named ``name`` given another coloured mark and other words."""
    at = PAGE.index(f'<a id="img-ouv_{name}"')
    end = PAGE.index("</a>", at)
    piece = PAGE[at:end]
    assert f'src="svg/{mark}.svg"' in piece and CLOSED in piece
    piece = piece.replace(f'src="svg/{mark}.svg"', f'src="svg/{new_mark}.svg"').replace(
        CLOSED, f'<img src="images/icons/open.svg" />{said}')
    return PAGE[:at] + piece + PAGE[end:]


def test_the_preseason_mountain_reads_its_lifts_trails_and_parks():
    # Windham's live map on 2026-11-26, before opening: nine lifts, 54 trails and four parks, none open.
    feed = windham.parse(PAGE, NOW)
    assert feed["Name"] == "Windham" and feed["LastUpdate"] == "2026-11-26T18:00:00Z" and "SnowReport" not in feed
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Windham", 9, 54), ("Terrain Parks", 0, 4)]
    lifts = feed["MountainAreas"][0]["Lifts"]
    assert [lift["Name"] for lift in lifts] == [
        "Baker Double", "East Peak Express Quad", "Enclave Carpet", "K Lift", "Westside Six",
        "Whisper Run Upper Carpet", "Whiteway Express Quad", "Wonderama Express Quad", "Wooly Bear Carpet Upper"]
    assert lifts[0] == {"Name": "Baker Double", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}
    assert {lift["StatusEnglish"] for lift in lifts} == {"closed"}
    trails = {trail["Name"]: trail for trail in feed["MountainAreas"][0]["Trails"]}
    assert len(trails) == 54
    assert trails["Whisper Run"] == {"Name": "Whisper Run", "Status": "Closed", "StatusEnglish": "closed",
                                     "Difficulty": "Green"}
    assert [sum(trail["Difficulty"] == level for trail in trails.values())
            for level in ("Green", "Blue", "Black", "Double black")] == [12, 26, 8, 8]
    # A trail the mountain has taken out of use is said so, and is not closed for the day.
    assert trails["Wosie's Way"]["Status"] == "Out of operations"
    assert sum(trail["StatusEnglish"] == "closed" for trail in trails.values()) == 53
    parks = feed["MountainAreas"][1]["Trails"]
    assert [park["Name"] for park in parks] == ["Wilbur Park", "Lower Warpath Park", "Lower Whirlwind Park",
                                                "Mini Park"]
    assert {park["Difficulty"] for park in parks} == {""}


def test_an_open_lift_and_an_open_trail_are_read():
    lifts = windham.parse(marker("Westside_Six", "carre-rouge", "carre-vert", "Open"), NOW)["MountainAreas"][0]["Lifts"]
    assert lifts[4] == {"Name": "Westside Six", "Status": "Open", "StatusEnglish": "open", "Difficulty": None}
    assert sum(lift["StatusEnglish"] == "open" for lift in lifts) == 1
    trails = windham.parse(marker("Whisper_Run", "2", "1", "Open"), NOW)["MountainAreas"][0]["Trails"]
    assert trails[0] == {"Name": "Whisper Run", "Status": "Open", "StatusEnglish": "open", "Difficulty": "Green"}


def test_a_lift_that_is_expected_or_on_hold_is_carried_in_the_map_s_words():
    lifts = windham.parse(marker("K_Lift", "carre-rouge", "carre-orange", "On hold"), NOW)["MountainAreas"][0]["Lifts"]
    assert lifts[3] == {"Name": "K Lift", "Status": "On hold", "StatusEnglish": "on hold", "Difficulty": None}


def test_a_map_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="statuses were not found"):
        windham.parse(changed('id="calque_ouverture"', 'id="calque"'), NOW)
    with pytest.raises(ValueError, match="K Lift is marked open but reads 'Closed'"):
        windham.parse(marker("K_Lift", "carre-rouge", "carre-vert", "Closed"), NOW)
    with pytest.raises(ValueError, match="K Lift is marked closed but reads 'Open'"):
        windham.parse(marker("K_Lift", "carre-rouge", "carre-rouge", "Open"), NOW)
    with pytest.raises(ValueError, match="a mark the reader does not know: carre-noir"):
        windham.parse(marker("K_Lift", "carre-rouge", "carre-noir", "Closed"), NOW)
    with pytest.raises(ValueError, match="a kind of marker the reader does not know: piste-orange"):
        windham.parse(changed("images/markers/piste-dbd.svg", "images/markers/piste-orange.svg", 1), NOW)
    with pytest.raises(ValueError, match="has 67 markers but 66 were read"):
        windham.parse(changed('<div class="toggle-marker"></div>', "", 1), NOW)
    with pytest.raises(ValueError, match="no lifts or no trails"):
        windham.parse(re.sub(r"images/markers/prl_\w+\.svg", "images/markers/piste-gc.svg", PAGE), NOW)
    with pytest.raises(ValueError):
        windham.parse("<html><body>Not the map</body></html>", NOW)
