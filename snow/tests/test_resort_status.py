import json

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
