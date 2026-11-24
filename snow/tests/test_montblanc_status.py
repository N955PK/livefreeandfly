from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import montblanc

# The framed table with its scripts, styles and its components' saved state taken out; the reader gives the same on
# the whole page, and on the page as it comes when English is asked for.
PAGE = (Path(__file__).parent / "fixtures" / "montblanc.html").read_text()
NOW = datetime(2026, 11, 25, 0, 0, tzinfo=timezone.utc)
CLOSED = 'title="Fermé" aria-label="Fermé"'


def changed(old: str, new: str, count: int = -1) -> str:
    assert old in PAGE
    return PAGE.replace(old, new, count)


def test_the_closed_mountain_reads_each_mountain_with_its_lifts_and_trails():
    # Mont Blanc's table on 2026-11-24, before the season, in French: seven lifts and 51 trails, all closed.
    feed = montblanc.parse(PAGE, NOW)
    assert feed["Name"] == "Mont Blanc" and feed["LastUpdate"] == "2026-11-25T00:00:00Z"
    assert "SnowReport" not in feed
    assert [(area["Name"], [lift["Name"] for lift in area["Lifts"]], len(area["Trails"]))
            for area in feed["MountainAreas"]] == [
        ("Mont Blanc", ["Tapis Blanc", "Triple Blanc", "Quad Blanc"], 22),
        ("Mont Faustin", ["Triple Faustin", "Quad Faustin", "Tapis Faustin"], 15),
        ("Mont Blanc Nord", ["Quad Nord"], 14)]
    lifts = [lift for area in feed["MountainAreas"] for lift in area["Lifts"]]
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    assert len(lifts) == 7
    assert lifts[4] == {"Name": "Quad Faustin", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}
    assert {row["StatusEnglish"] for row in lifts + trails} == {"closed"}
    # "1 - Yodel" is the trail Yodel; the lodges (Chalet Principal, Refuge Nord) and the touring routes are left out.
    assert trails[0] == {"Name": "Yodel", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": "Green"}
    names = {trail["Name"] for trail in trails}
    assert "L'Extrême" in names and not names & {"Chalet Principal", "Refuge Nord", "Montée Yodel | Mont Blanc"}
    levels = {trail["Name"]: trail["Difficulty"] for trail in trails}
    assert (levels["Robert"], levels["Couloir"], levels["L'Extrême"], levels["Nitro"], levels["MBPark"]) == (
        "Blue", "Black", "Double black", "", "")


def test_the_page_s_status_words_are_read_in_french_and_in_english():
    # The first symbol on the page is the Tapis Blanc's under skiing, the second its symbol under services.
    feed = montblanc.parse(changed(CLOSED, 'title="Ouvert" aria-label="Ouvert"', 2), NOW)
    carpet = feed["MountainAreas"][0]["Lifts"][0]
    assert (carpet["Name"], carpet["Status"], carpet["StatusEnglish"]) == ("Tapis Blanc", "Open", "open")
    assert feed["MountainAreas"][0]["Lifts"][1]["StatusEnglish"] == "closed"
    # A lift's status is its symbol under services, not the one under skiing.
    feed = montblanc.parse(changed(CLOSED, 'title="Ouvert" aria-label="Ouvert"', 1), NOW)
    assert feed["MountainAreas"][0]["Lifts"][0]["StatusEnglish"] == "closed"
    english = PAGE.replace(CLOSED, 'title="Closed" aria-label="Closed"')
    assert montblanc.parse(english, NOW) == montblanc.parse(PAGE, NOW)
    for said, status, word in (("Open", "Open", "open"), ("Attention !", "Caution", "open"),
                               ("Piste glacée", "Icy", "open"), ("Faible visibilité", "Low visibility", "open"),
                               ("Ouverture retardée", "Delayed", "delayed"), ("Maintenance", "Maintenance", "closed")):
        feed = montblanc.parse(changed(CLOSED, f'title="{said}" aria-label="{said}"'), NOW)
        rows = [row for area in feed["MountainAreas"] for row in area["Lifts"] + area["Trails"]]
        assert len(rows) == 58 and {(row["Status"], row["StatusEnglish"]) for row in rows} == {(status, word)}


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="status symbols"):
        montblanc.parse(changed(CLOSED, 'title="Vent" aria-label="Vent"', 1), NOW)
    with pytest.raises(ValueError, match="difficulty drawing"):
        montblanc.parse(changed('fill="#1176BC"', 'fill="#0000FF"'), NOW)
    with pytest.raises(ValueError, match="not a name, a bar and a mountain"):
        montblanc.parse(changed("Quad Nord | Mont Blanc Nord", "Quad Nord"), NOW)
    with pytest.raises(ValueError, match="which the page has no trails for"):
        montblanc.parse(changed("Quad Nord | Mont Blanc Nord", "Quad Nord | Mont Rouge"), NOW)
    with pytest.raises(ValueError, match="MONT BLANC lists no trails"):
        montblanc.parse(changed("<div data-flux-widget-trail>", "<div data-flux-widget-row>"), NOW)
    with pytest.raises(ValueError, match="no lifts or no trails"):
        montblanc.parse("<html><body>GetTrail.info</body></html>", NOW)
