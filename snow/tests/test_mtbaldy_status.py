import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import mtbaldy

# The feed as tickets.mtbaldyresort.com/api/status gave it on 2026-11-26, the mountain's opening day (the names of
# the staff who wrote the report and the video list removed).
PAGE = (Path(__file__).parent / "fixtures" / "mtbaldy.json").read_text()
# Thanksgiving morning at 9:55 in Los Angeles, inside the day's 9 AM to 5 PM.
NOW = datetime(2026, 11, 26, 17, 55, tzinfo=timezone.utc)


def changed(change) -> str:
    """The feed changed by ``change``."""
    feed = json.loads(PAGE)
    change(feed)
    return json.dumps(feed)


def lifts(feed: dict) -> list:
    return [(area["Lifts"][0]["Name"], area["Lifts"][0]["Status"], area["Lifts"][0]["StatusEnglish"])
            for area in feed["MountainAreas"]]


def test_each_chair_is_read_with_the_runs_skied_from_it():
    feed = mtbaldy.parse(PAGE, NOW)
    assert feed["Name"] == "Mt. Baldy" and feed["LastUpdate"] == "2026-11-26T17:55:00Z"
    assert lifts(feed) == [("Chair 1 · Sugar Pine", "Scenic rides only", "open"),
                           ("Chair 2 · The Gulch", "Open", "open"),
                           ("Chair 3 · Thunder Mountain", "Pray for snow", "closed"),
                           ("Chair 4 · West Side", "Pray for snow", "closed")]
    assert feed["MountainAreas"][0]["Lifts"] == [{"Name": "Chair 1 · Sugar Pine", "Status": "Scenic rides only",
                                                  "StatusEnglish": "open", "Difficulty": None}]
    assert [len(area["Trails"]) for area in feed["MountainAreas"]] == [7, 3, 17, 4]
    trails = {trail["Name"]: trail for area in feed["MountainAreas"] for trail in area["Trails"]}
    assert len(trails) == 31 and sum(trail["StatusEnglish"] == "open" for trail in trails.values()) == 3
    assert trails["Beginner's Gulch"] == {"Name": "Beginner's Gulch", "Status": "Ungroomed", "StatusEnglish": "open",
                                          "Difficulty": "Green", "Grooming": "No"}
    assert trails["Bonanza"] == {"Name": "Bonanza", "Status": "Closed", "StatusEnglish": "closed",
                                 "Difficulty": "Blue", "Grooming": "No"}
    # The freestyle terrain has no level, and the grooming report has not covered Chair 1's runs.
    assert trails["Freestyle terrain"]["Difficulty"] == "" and trails["Goldridge"]["Difficulty"] == "Black"
    assert trails["Windslab"] == {"Name": "Windslab", "Status": "Not reported", "StatusEnglish": "not reported",
                                  "Difficulty": "Double black"}
    # The opening day's report has no base depth and no new snow, so there is no snow report.
    assert "SnowReport" not in feed


def test_a_running_chair_is_open_only_inside_the_day_s_hours():
    # The report's "open" stays up all night: at 9:40 that evening, and at 8 in the morning, nothing is open.
    evening = mtbaldy.parse(PAGE, datetime(2026, 11, 27, 5, 40, tzinfo=timezone.utc))
    assert {plain for _, _, plain in lifts(evening)} == {"closed"}
    assert lifts(evening)[1] == ("Chair 2 · The Gulch", "Closed", "closed")
    early = mtbaldy.parse(PAGE, datetime(2026, 11, 26, 16, 0, tzinfo=timezone.utc))
    assert lifts(early)[:2] == [("Chair 1 · Sugar Pine", "Opens 9 AM", "closed"),
                                ("Chair 2 · The Gulch", "Opens 9 AM", "closed")]
    after = mtbaldy.parse(PAGE, datetime(2026, 11, 27, 1, 0, tzinfo=timezone.utc))
    assert lifts(after)[1] == ("Chair 2 · The Gulch", "Closed", "closed")
    # A chair with an opening time of its own opens then.
    late = changed(lambda feed: feed["report"]["chairs"]["2"].update(opens="10:30"))
    assert lifts(mtbaldy.parse(late, NOW))[1] == ("Chair 2 · The Gulch", "Opens 10:30 AM", "closed")
    # A day the lifts do not run.
    shut = changed(lambda feed: feed["openHours"]["days"][0].update(open=False))
    assert {plain for _, _, plain in lifts(mtbaldy.parse(shut, NOW))} == {"closed"}


def test_the_other_statuses_are_carried_in_the_page_s_words():
    def other(feed):
        feed["report"]["chairs"]["1"] = {"status": "hold", "note": "", "opens": "11:00"}
        feed["report"]["chairs"]["2"]["status"] = "closed"
        del feed["report"]["chairs"]["4"]
        feed["runs"][0]["status"], feed["runs"][1]["status"], feed["runs"][2]["status"] = "groomed", "powder", "moguls"

    feed = mtbaldy.parse(changed(other), NOW)
    assert lifts(feed) == [("Chair 1 · Sugar Pine", "On hold", "on hold"),
                           ("Chair 2 · The Gulch", "Closed", "closed"),
                           ("Chair 3 · Thunder Mountain", "Pray for snow", "closed"),
                           ("Chair 4 · West Side", "Pray for snow", "closed")]
    gulch = feed["MountainAreas"][1]["Trails"]
    assert [(trail["Status"], trail["StatusEnglish"], trail["Grooming"]) for trail in gulch] == [
        ("Groomed", "open", "Yes"), ("Powder", "open", "No"), ("Moguls", "open", "No")]


def test_the_snow_report_gives_the_base_depth_and_new_snow_in_inches():
    filled = changed(lambda feed: feed["report"].update(base=24, newSnow="6", surface="Packed powder"))
    report = mtbaldy.parse(filled, NOW)["SnowReport"]
    assert report["LastUpdate"] == "2026-11-26T05:38:51Z" and report["Resortwide"] is True
    assert report["BaseArea"] == {"Name": "Mountain", "BaseIn": 24.0, "Last24HoursIn": 6.0}
    assert report["BaseConditions"] == "Packed powder" and report["SeasonTotalIn"] is None
    assert report["Report"].startswith("Happy Thanksgiving from Mt Baldy!")
    # A base depth with no new snow figure, and new snow over a base nobody filled in.
    assert mtbaldy.parse(changed(lambda feed: feed["report"].update(base=18.5)), NOW)["SnowReport"]["BaseArea"] == {
        "Name": "Mountain", "BaseIn": 18.5}
    assert mtbaldy.parse(changed(lambda feed: feed["report"].update(base=0, newSnow=3)), NOW)["SnowReport"][
        "BaseArea"] == {"Name": "Mountain", "Last24HoursIn": 3.0}


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    for figures in ({"base": "deep"}, {"base": 0, "newSnow": 0}, {"base": 24, "at": "yesterday"}, {"base": True}):
        feed = mtbaldy.parse(changed(lambda feed: feed["report"].update(figures)), NOW)
        assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 4


def test_a_feed_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="no chairs or no runs"):
        mtbaldy.parse(changed(lambda feed: feed.update(chairs=[])), NOW)
    with pytest.raises(ValueError, match="no chairs or no runs"):
        mtbaldy.parse(changed(lambda feed: feed.pop("runs")), NOW)
    with pytest.raises(ValueError, match="no report of the chairs"):
        mtbaldy.parse(changed(lambda feed: feed.update(report=None)), NOW)
    with pytest.raises(ValueError, match="for the summer season"):
        mtbaldy.parse(changed(lambda feed: feed.update(season="summer")), NOW)
    with pytest.raises(ValueError, match="not the winter"):
        mtbaldy.parse(changed(lambda feed: feed["report"].update(season="summer")), NOW)
    with pytest.raises(ValueError, match="'spinning', which the reader does not know"):
        mtbaldy.parse(changed(lambda feed: feed["report"]["chairs"]["2"].update(status="spinning")), NOW)
    with pytest.raises(ValueError, match="'icy', which the reader does not know"):
        mtbaldy.parse(changed(lambda feed: feed["runs"][0].update(status="icy")), NOW)
    with pytest.raises(ValueError, match="the level 'pro'"):
        mtbaldy.parse(changed(lambda feed: feed["runs"][0].update(level="pro")), NOW)
    with pytest.raises(ValueError, match="which is not listed"):
        mtbaldy.parse(changed(lambda feed: feed["runs"][0].update(chair=5)), NOW)
    with pytest.raises(ValueError, match="lists a run twice"):
        mtbaldy.parse(changed(lambda feed: feed["runs"][1].update(name="Beginner's Gulch")), NOW)
    with pytest.raises(ValueError, match="listed twice"):
        mtbaldy.parse(changed(lambda feed: feed["chairs"][1].update(n=1)), NOW)
    with pytest.raises(ValueError, match="does not give the days the lifts run"):
        mtbaldy.parse(changed(lambda feed: feed.pop("openHours")), NOW)
    with pytest.raises(ValueError, match="do not cover 2027-01-15"):
        mtbaldy.parse(PAGE, datetime(2027, 1, 15, 18, 0, tzinfo=timezone.utc))
    with pytest.raises(ValueError, match="not a time of day"):
        mtbaldy.parse(changed(lambda feed: feed["openHours"]["days"][0].update(to="dusk")), NOW)
    with pytest.raises(ValueError, match="not in the shape"):
        mtbaldy.parse("[]", NOW)
    with pytest.raises(ValueError):
        mtbaldy.parse("<html><body>Not the feed</body></html>", NOW)
