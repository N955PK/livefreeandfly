import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import massanutten

FIXTURES = Path(__file__).parent / "fixtures"
# The page cut down to its three status blocks, drawings out, and the status as the site answered the page's own
# request; the reader gives the same on the whole page.
PAGES = {"page": (FIXTURES / "massanutten_page.html").read_text(),
         "status": (FIXTURES / "massanutten_status.json").read_text()}
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)
CREEKSIDE, BOARDWALK = "6ae46c2998a2085409d45102", "6ae46c5b98a2085409d45109"


def status(change) -> dict:
    """The pages with the flattened status changed: ``change`` is given the list and where its answer's parts are."""
    values = json.loads(PAGES["status"])
    change(values, values[values[0]["lifts"]], values[values[0]["trails"]])
    return {**PAGES, "status": json.dumps(values)}


def page(old: str, new: str, count: int = -1) -> dict:
    assert old in PAGES["page"]
    return {**PAGES, "page": PAGES["page"].replace(old, new, count)}


def test_the_closed_mountain_reads_its_lifts_and_the_trails_of_each_difficulty():
    # Massanutten's page and status on 2026-11-26, before it opened: seven lifts and 23 trails, all closed.
    feed = massanutten.parse(PAGES, NOW)
    assert feed["Name"] == "Massanutten" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    assert "SnowReport" not in feed
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Massanutten", 7, 0), ("Easiest", 0, 6), ("More Difficult", 0, 9), ("Most Difficult", 0, 5),
        ("Extreme Difficulty", 0, 1), ("Freestyle Terrain", 0, 2)]
    lifts = feed["MountainAreas"][0]["Lifts"]
    assert lifts[0] == {"Name": "Creekside", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}
    assert [lift["Name"] for lift in lifts[1:3]] == ["Easy Rider", "Peak Express"] and lifts[-1]["Name"] == "Sunkid"
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    assert {trail["StatusEnglish"] for trail in trails + lifts} == {"closed"}
    assert trails[0] == {"Name": "Boardwalk", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": "Green",
                         "Grooming": "No"}
    assert trails[3]["Name"] == "Paul's Way" and trails[-1]["Name"] == "Pacesetter"
    assert [area["Trails"][0]["Difficulty"] for area in feed["MountainAreas"][1:]] == [
        "Green", "Blue", "Black", "Double black", ""]


def test_an_open_lift_and_a_groomed_open_trail_are_read_from_the_status():
    def opened(values, lifts, trails):
        # Every value inside the answer is written as its position in the list.
        at = len(values)
        values.extend(["open", {"status": at, "hours": values[lifts[CREEKSIDE]]["hours"]}, True, "groomed", [at + 3],
                       {"open": at + 2, "features": at + 4}])
        lifts[CREEKSIDE], trails[BOARDWALK] = at + 1, at + 5

    feed = massanutten.parse(status(opened), NOW)
    assert [lift["StatusEnglish"] for lift in feed["MountainAreas"][0]["Lifts"]][:2] == ["open", "closed"]
    assert feed["MountainAreas"][1]["Trails"][0] == {"Name": "Boardwalk", "Status": "Open", "StatusEnglish": "open",
                                                     "Difficulty": "Green", "Grooming": "Yes"}

    def held(values, lifts, trails):
        values.extend(["hold", {"status": len(values), "hours": values[lifts[CREEKSIDE]]["hours"]}])
        lifts[CREEKSIDE] = len(values) - 1

    lift = massanutten.parse(status(held), NOW)["MountainAreas"][0]["Lifts"][0]
    assert (lift["Name"], lift["Status"], lift["StatusEnglish"]) == ("Creekside", "On hold", "on hold")


def test_a_page_or_a_status_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="are not the ones the status gives"):
        massanutten.parse(page(CREEKSIDE, "0" * 24), NOW)
    with pytest.raises(ValueError, match="are not the ones the status gives"):
        massanutten.parse(status(lambda values, lifts, trails: trails.pop(BOARDWALK)), NOW)
    with pytest.raises(ValueError, match="a heading the reader does not know: 'Glades'"):
        massanutten.parse(page(">Freestyle Terrain</span>", ">Glades</span>"), NOW)
    with pytest.raises(ValueError, match="list of lifts was not found"):
        massanutten.parse(page("data-lift-trail-block=\"lifts\"", "data-block=\"lifts\""), NOW)

    def unknown(values, lifts, trails):
        values[values[lifts[CREEKSIDE]]["status"]] = "standby"

    with pytest.raises(ValueError, match="Creekside has a state the reader does not know: 'standby'"):
        massanutten.parse(status(unknown), NOW)
    with pytest.raises(ValueError, match="status is not available"):
        massanutten.parse(status(lambda values, lifts, trails: values.__setitem__(1, False)), NOW)
    with pytest.raises(ValueError, match="the status could not be read"):
        massanutten.parse({**PAGES, "status": "<html><body>Page not found</body></html>"}, NOW)
    with pytest.raises(ValueError, match="the status could not be read"):
        massanutten.parse({**PAGES, "status": "[{\"available\": 9}]"}, NOW)
    with pytest.raises(ValueError, match="list of lifts was not found"):
        massanutten.parse({**PAGES, "page": "<html><body>Page not found</body></html>"}, NOW)
