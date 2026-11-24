import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import resort_status


def page(feed: dict) -> str:
    return f"<script>FR.TerrainStatusFeed = {json.dumps(feed)};</script>"


def test_a_feed_with_lifts_and_trails_is_read():
    feed = {"IsSuccessful": True, "Lifts": [{"Name": "Chair 1", "Status": 1, "Mountain": "Frontside"}],
            "GroomingAreas": [{"Name": "Frontside", "Trails": [{"Name": "Run", "IsOpen": True, "Difficulty": 2}]}]}
    assert resort_status.feed_of(page(feed)) == feed


def test_a_preseason_feed_with_empty_areas_is_no_status_not_an_empty_mountain():
    feed = {"IsSuccessful": True, "Lifts": [],
            "GroomingAreas": [{"Name": "Bowls", "Trails": [], "Lifts": []}, {"Name": "Frontside", "Trails": [], "Lifts": []}]}
    with pytest.raises(ValueError, match="no lifts or trails"):
        resort_status.feed_of(page(feed))


def test_trails_alone_are_enough_to_publish():
    feed = {"IsSuccessful": True, "Lifts": [],
            "GroomingAreas": [{"Name": "Frontside", "Trails": [{"Name": "Run", "IsOpen": False, "Difficulty": 1}]}]}
    assert resort_status.feed_of(page(feed)) == feed


def test_an_unsuccessful_feed_is_refused():
    with pytest.raises(ValueError, match="error"):
        resort_status.feed_of(page({"IsSuccessful": False, "ErrorDetails": "down"}))


def test_a_trail_carries_its_grooming_only_when_the_resort_says():
    said = resort_status.trail_row({"Name": "Run", "IsOpen": True, "Difficulty": 2, "IsGroomed": True})
    unsaid = resort_status.trail_row({"Name": "Run", "IsOpen": True, "Difficulty": 2, "IsGroomed": None})
    assert said["Grooming"] == "Yes" and "Grooming" not in unsaid
    assert resort_status.trail_row({"Name": "Run", "IsOpen": False, "Difficulty": 2, "IsGroomed": False})["Grooming"] == "No"


FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 11, 23, 21, 0, tzinfo=timezone.utc)


def fixture_feed(name: str) -> dict:
    return resort_status.feed_of((FIXTURES / f"vail_{name}.html").read_text())


def test_the_new_england_resorts_are_read_from_their_own_sites_under_their_mountain_keys():
    assert {"stowe", "okemo", "mountsnow", "wildcat", "attitash", "sunapee", "crotched", "parkcity", "vail", "beavercreek", "breckenridge", "keystone", "crestedbutte"} <= set(resort_status.RESORTS)
    assert resort_status.RESORTS["stowe"][1] == "www.stowe.com"
    assert resort_status.RESORTS["sunapee"][2] == "lift-and-terrain-status.aspx"


def test_stevens_pass_is_read_from_its_own_site_and_is_left_out_until_it_posts_its_lifts():
    # Stevens Pass names its page lift-and-terrain; on November 23 its seven areas were all still empty.
    assert resort_status.RESORTS["stevens"] == ("Stevens Pass", "www.stevenspass.com", "lift-and-terrain-status.aspx")
    with pytest.raises(ValueError, match="no lifts or trails"):
        resort_status.feed_of((FIXTURES / "vail_stevens_preseason.html").read_text())


def test_a_closed_mountain_that_lists_its_lifts_reads_as_every_lift_closed():
    # Stowe's page as it was the week before Thanksgiving: lifts and trails listed, nothing turning.
    feed = resort_status.recast("Stowe", fixture_feed("stowe"), NOW)
    lifts = [lift for area in feed["MountainAreas"] for lift in area["Lifts"]]
    trails = [trail for area in feed["MountainAreas"] for trail in area["Trails"]]
    assert len(lifts) == 7 and len(trails) == 6
    assert {lift["StatusEnglish"] for lift in lifts} == {"closed"} and {trail["StatusEnglish"] for trail in trails} == {"closed"}
    assert all(lift["Name"] for lift in lifts) and {area["Name"] for area in feed["MountainAreas"]} == {"Spruce Peak", "Mt. Mansfield - Gondola"}


def test_open_and_scheduled_lifts_and_a_hold_keep_the_words_the_page_sorts_on():
    feed = resort_status.recast("Heavenly", fixture_feed("heavenly"), NOW)
    states = {lift["StatusEnglish"] for area in feed["MountainAreas"] for lift in area["Lifts"]}
    assert states == {"open", "closed", "scheduled"}
    assert resort_status.lift_row({"Name": "Lift", "Status": 2})["StatusEnglish"] == "hold"


def test_a_resort_with_nothing_posted_before_its_season_is_left_out():
    with pytest.raises(ValueError, match="no lifts or trails"):
        resort_status.feed_of((FIXTURES / "vail_crotched_preseason.html").read_text())


def test_one_resort_that_fails_costs_none_of_the_others(tmp_path, monkeypatch):
    pages = {"www.stowe.com": "stowe", "www.skiheavenly.com": "heavenly"}

    def fetch(host, page):
        if host == "www.crotchedmtn.com":
            return resort_status.feed_of((FIXTURES / "vail_crotched_preseason.html").read_text())
        if host not in pages:
            raise ConnectionError("down")
        return fixture_feed(pages[host])

    monkeypatch.setattr(resort_status, "fetch", fetch)
    out = tmp_path / "resort_status.json"
    assert resort_status.main(str(out)) == 0
    assert set(json.loads(out.read_text())["resorts"]) == {"stowe", "heavenly"}


def test_when_every_resort_fails_no_file_is_written(tmp_path, monkeypatch):
    def fetch(host, page):
        raise ConnectionError("down")

    monkeypatch.setattr(resort_status, "fetch", fetch)
    out = tmp_path / "resort_status.json"
    assert resort_status.main(str(out)) == 1 and not out.exists()
