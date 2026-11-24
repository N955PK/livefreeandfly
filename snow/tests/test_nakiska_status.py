from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import nakiska

FIXTURES = Path(__file__).parent / "fixtures"
# The frame that fills the snow report page, whole, and of the open runs report only its two tables; the reader
# gives the same on the whole page.
PAGES = {name: (FIXTURES / f"nakiska_{name}.html").read_text() for name in nakiska.URLS}
NOW = datetime(2026, 11, 24, 23, 40, tzinfo=timezone.utc)
CLOSED = "<span style='font-weight:bold;font-family:montserrat;'>CLOSED</span>"
RUN = ("<tr><td style='text-align:center;'><div class='groomrunnum'>#1</div><span class='run-name'>{name}</span>"
       "<div class='ski-difficulty'><span class='{level}'></span><div></td></tr>")


def page(name: str, old: str, new: str, count: int = -1) -> dict:
    assert old in PAGES[name]
    return {**PAGES, name: PAGES[name].replace(old, new, count)}


def test_the_mountain_between_weekends_reads_its_lifts_and_its_open_runs():
    # Nakiska on 2026-11-24, shut between its preview weekends: 6 lifts, all closed, and the 6 runs it lists open.
    feed = nakiska.parse(PAGES, NOW)
    assert feed["Name"] == "Nakiska" and feed["LastUpdate"] == "2026-11-24T23:40:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Nakiska", 6, 6)]
    lifts = feed["MountainAreas"][0]["Lifts"]
    assert [lift["Name"] for lift in lifts] == ["Gold Chair", "Silver Chair", "Bronze Chair", "Olympic Chair",
                                                "Ninja Magic Carpet", "Monster Magic Carpet"]
    assert lifts[0] == {"Name": "Gold Chair", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}
    assert {lift["StatusEnglish"] for lift in lifts} == {"closed"}
    trails = feed["MountainAreas"][0]["Trails"]
    assert trails[0] == {"Name": "Olympic Easy Way", "Status": "Open", "StatusEnglish": "open", "Difficulty": "Green"}
    assert [(trail["Name"], trail["Difficulty"]) for trail in trails[3:]] == [
        ("Upper Mapmaker", "Blue"), ("Walking Buffalo", "Blue"), ("Middle Mapmaker", "Blue")]
    # The site lists only the open runs, and does not say which are groomed.
    assert {trail["StatusEnglish"] for trail in trails} == {"open"} and all("Grooming" not in t for t in trails)


def test_the_snow_report_is_in_inches_from_the_frame_s_centimetres():
    snow = nakiska.parse(PAGES, NOW)["SnowReport"]
    # "NOVEMBER 24, 2026 | 10:47am": Alberta keeps one time all year, six hours behind UTC.
    assert snow["LastUpdate"] == "2026-11-24T16:47:00Z" and snow["Resortwide"] is True
    # A 41 cm snow pack, nothing new in 48 hours, 14 cm in 7 days and 48 cm this year.
    assert snow["BaseArea"] == {"Name": "Nakiska", "BaseIn": 16.1, "OvernightIn": 0.0, "Last24HoursIn": 0.0,
                                "Last48HoursIn": 0.0, "Last7DaysIn": 5.5}
    assert snow["SeasonTotalIn"] == 18.9
    assert snow["BaseConditions"] == "Machine Groomed (upper), Powder (lower)"
    same = nakiska.parse(page("status", "\"Powder<span", "\"Machine Groomed<span"), NOW)["SnowReport"]
    assert same["BaseConditions"] == "Machine Groomed"


def test_open_lifts_and_runs_in_both_parts_of_the_mountain_are_read():
    pages = page("status", f"GOLD CHAIR: {CLOSED}", "GOLD CHAIR: <span style='color:#004b85;'>OPEN</span>")
    pages["status"] = pages["status"].replace("getElementById('snowReportLiftsOpen').innerHTML= '0'",
                                              "getElementById('snowReportLiftsOpen').innerHTML= '1'")
    glades = "<div class='bowl-title'>Monster Glades</div></th></tr></thead><tbody>"
    assert glades in pages["runs"]
    pages["runs"] = pages["runs"].replace(glades, glades + RUN.format(name="Monster Glade 1", level="black-diamond")
                                          + RUN.format(name="Homesteader", level="green-circle-blue-square")
                                          + RUN.format(name="Red Crow", level="double-black-diamond"))
    feed = nakiska.parse(pages, NOW)
    assert [(lift["Name"], lift["Status"]) for lift in feed["MountainAreas"][0]["Lifts"]][:2] == [
        ("Gold Chair", "Open"), ("Silver Chair", "Closed")]
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Nakiska", 6, 6), ("Monster Glades", 0, 3)]
    assert [(trail["Name"], trail["Difficulty"]) for trail in feed["MountainAreas"][1]["Trails"]] == [
        ("Monster Glade 1", "Black"), ("Homesteader", "Blue"), ("Red Crow", "Double black")]


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="Gold Chair has a status the reader does not know: 'ON HOLD'"):
        nakiska.parse(page("status", f"GOLD CHAIR: {CLOSED}", "GOLD CHAIR: <span>ON HOLD</span>"), NOW)
    with pytest.raises(ValueError, match="counts '1' lifts operating but 0 of 6"):
        nakiska.parse(page("status", "getElementById('snowReportLiftsOpen').innerHTML= '0'",
                           "getElementById('snowReportLiftsOpen').innerHTML= '1'"), NOW)
    with pytest.raises(ValueError, match="sets no figures"):
        nakiska.parse({**PAGES, "status": "<html><body>Welcome</body></html>"}, NOW)
    with pytest.raises(ValueError, match="lists no lifts"):
        nakiska.parse({**PAGES, "status": PAGES["status"].replace("CHAIR: ", "CHAIR - ")
                       .replace("CARPET: ", "CARPET - ")}, NOW)
    with pytest.raises(ValueError, match="open runs report was not found"):
        nakiska.parse(page("runs", "table-groom table-bowl", "table-runs"), NOW)
    with pytest.raises(ValueError, match="Amphitheater has a difficulty the reader does not know: 'orange-oval'"):
        nakiska.parse(page("runs", "Amphitheater</span><div class='ski-difficulty'><span class='green-circle'>",
                           "Amphitheater</span><div class='ski-difficulty'><span class='orange-oval'>"), NOW)
    with pytest.raises(ValueError, match="Nakiska lists 6 runs but 5"):
        nakiska.parse(page("runs", "<div class='ski-difficulty'>", "<div class='difficulty'>", 1), NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    for old, new in (("getElementById('snowReportNewSnowFallPack').innerHTML= \"41 \"",
                      "getElementById('snowReportNewSnowFallPack').innerHTML= \"deep \""),
                     ("getElementById('snowReportNewSnowFall24').innerHTML= \"0 \"",
                      "getElementById('snowReportNewSnowFall24').innerHTML= \"\""),
                     ("getElementById('snowReportTH_SnowreportRecentSnowSaveDate').innerHTML= \"NOVEMBER 24, 2026 | "
                      "10:47am \"",
                      "getElementById('snowReportTH_SnowreportRecentSnowSaveDate').innerHTML= \"TODAY\"")):
        feed = nakiska.parse(page("status", old, new), NOW)
        assert "SnowReport" not in feed and len(feed["MountainAreas"][0]["Lifts"]) == 6
