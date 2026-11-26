import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import showdown

FIXTURES = Path(__file__).parent / "fixtures"
# The two Firestore documents the page's scripts fetch, with the fields naming the member of staff taken out.
PAGES = {name: (FIXTURES / f"showdown_{name}.json").read_text() for name in showdown.URLS}
NOW = datetime(2026, 11, 26, 17, 0, tzinfo=timezone.utc)


def edited(which: str, change) -> dict:
    """The documents with one of them changed: ``change`` is given its fields to alter."""
    data = json.loads(PAGES[which])
    change(data["fields"])
    return {**PAGES, which: json.dumps(data)}


def lift(fields: dict, at: int) -> dict:
    return fields["lifts"]["arrayValue"]["values"][at]["mapValue"]["fields"]


def run(fields: dict, part: int, at: int) -> dict:
    runs = fields["areas"]["arrayValue"]["values"][part]["mapValue"]["fields"]["runs"]
    return runs["arrayValue"]["values"][at]["mapValue"]["fields"]


def test_the_documents_are_the_two_the_page_s_scripts_fetch():
    base = "https://firestore.googleapis.com/v1/projects/showdown-task/databases/(default)/documents/"
    assert list(showdown.URLS) == ["trails", "snow"]
    assert showdown.URLS["trails"].startswith(base + "trailstatus/current?key=")
    assert showdown.URLS["snow"].startswith(base + "snowreport/current?key=")


def test_the_closed_mountain_reads_its_lifts_and_each_part_s_trails():
    # Showdown's documents on 2026-11-26, before it opened: four lifts and 38 trails, all closed.
    feed = showdown.parse(PAGES, NOW)
    assert feed["Name"] == "Showdown" and feed["LastUpdate"] == "2026-11-26T17:00:00Z"
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Showdown", 4, 0), ("Northside", 0, 14), ("Main Face", 0, 9), ("Ruby Bowl", 0, 15)]
    lifts = feed["MountainAreas"][0]["Lifts"]
    assert [row["Name"] for row in lifts] == ["Prospector", "Payload", "Caboose", "Learning Conveyor"]
    assert lifts[0] == {"Name": "Prospector", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    assert len(trails) == 38 == len({trail["Name"] for trail in trails})
    assert {row["StatusEnglish"] for row in lifts + trails} == {"closed"}
    assert trails[0] == {"Name": "Prentice", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": "Green",
                         "Grooming": "No"}
    count = {}
    for trail in trails:
        count[trail["Difficulty"]] = count.get(trail["Difficulty"], 0) + 1
    assert count == {"Green": 11, "Blue": 14, "Black": 13}


def test_the_snow_report_gives_both_depths_the_snowfall_and_the_surface():
    snow = showdown.parse(PAGES, NOW)["SnowReport"]
    # The document's "at" is 1795625795445 milliseconds, which the page shows as 9:56 am Mountain time on the 25th.
    assert snow["LastUpdate"] == "2026-11-25T16:56:35Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Base", "BaseIn": 5, "OvernightIn": 0, "Last24HoursIn": 0, "Last7DaysIn": 9,
                                "StormTotalIn": 0}
    assert snow["SummitArea"] == {"Name": "Summit", "BaseIn": 5}
    assert snow["SeasonTotalIn"] == 42 and snow["BaseConditions"] == "Powder, Variable"


def test_a_figure_left_empty_stays_empty_and_a_half_inch_is_kept():
    def change(fields):
        fields["summit"] = {"stringValue": ""}
        fields["last24"] = {"stringValue": "2.5\""}
        fields["secondary"] = {"stringValue": ""}
    snow = showdown.parse(edited("snow", change), NOW)["SnowReport"]
    assert snow["SummitArea"]["BaseIn"] is None and snow["BaseArea"]["Last24HoursIn"] == 2.5
    assert snow["BaseConditions"] == "Powder"


def test_an_open_lift_and_a_groomed_open_trail_read_as_open():
    def change(fields):
        lift(fields, 1)["open"] = {"booleanValue": True}
        run(fields, 0, 0).update(open={"booleanValue": True}, groomed={"booleanValue": True})
        fields["liftsOpen"] = fields["openCount"] = fields["groomedCount"] = {"integerValue": "1"}
    feed = showdown.parse(edited("trails", change), NOW)
    assert feed["MountainAreas"][0]["Lifts"][1] == {"Name": "Payload", "Status": "Open", "StatusEnglish": "open",
                                                    "Difficulty": None}
    assert feed["MountainAreas"][1]["Trails"][0] == {"Name": "Prentice", "Status": "Open", "StatusEnglish": "open",
                                                     "Difficulty": "Green", "Grooming": "Yes"}


def test_a_document_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="trailstatus document is not JSON"):
        showdown.parse({**PAGES, "trails": "<html>Sign in</html>"}, NOW)
    with pytest.raises(ValueError, match="trailstatus document was not found"):
        showdown.parse({**PAGES, "trails": '{"error": {"code": 403, "status": "PERMISSION_DENIED"}}'}, NOW)
    with pytest.raises(ValueError, match="trailstatus document was not found"):
        showdown.parse({**PAGES, "trails": PAGES["snow"]}, NOW)
    with pytest.raises(ValueError, match="lists no lifts or no trails"):
        showdown.parse(edited("trails", lambda fields: fields.pop("lifts")), NOW)
    with pytest.raises(ValueError, match="counts 5 lifts but 4 were read"):
        showdown.parse(edited("trails", lambda fields: fields.update(liftsTotal={"integerValue": "5"})), NOW)
    with pytest.raises(ValueError, match="counts 0 lifts open but 1 were read"):
        showdown.parse(edited("trails", lambda fields: lift(fields, 0).update(open={"booleanValue": True})), NOW)
    with pytest.raises(ValueError, match="counts 39 trails but 38 were read"):
        showdown.parse(edited("trails", lambda fields: fields.update(total={"integerValue": "39"})), NOW)
    with pytest.raises(ValueError, match="counts 0 trails groomed but 1 were read"):
        showdown.parse(edited("trails", lambda fields: run(fields, 2, 3).update(groomed={"booleanValue": True})), NOW)
    with pytest.raises(ValueError, match="Prentice has a difficulty the reader does not know: 'x'"):
        showdown.parse(edited("trails", lambda fields: run(fields, 0, 0).update(level={"stringValue": "x"})), NOW)
    with pytest.raises(ValueError, match="Prospector does not say whether it is open"):
        showdown.parse(edited("trails", lambda fields: lift(fields, 0).update(open={"stringValue": "yes"})), NOW)
    with pytest.raises(ValueError, match="a type the reader does not know: geoPointValue"):
        showdown.parse(edited("trails", lambda fields: fields.update(where={"geoPointValue": {}})), NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report(capsys):
    feed = showdown.parse(edited("snow", lambda fields: fields.update(base={"stringValue": "a foot"})), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 4
    assert "Showdown: snow report: the snow report's base reads 'a foot', not inches" in capsys.readouterr().out
    assert "SnowReport" not in showdown.parse(edited("snow", lambda fields: fields.pop("at")), NOW)
    assert "SnowReport" not in showdown.parse({**PAGES, "snow": "{}"}, NOW)
