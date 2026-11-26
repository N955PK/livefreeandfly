import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import sasquatch

# The two feeds as the site gave them on 2026-11-26: last season's last statuses (March 6) and snow report.
FIXTURES = Path(__file__).parent / "fixtures"
PAGES = {name: (FIXTURES / f"sasquatch_{name}.json").read_text() for name in ("lifts", "snow")}
# The morning the statuses were written, and the day the feeds were saved.
THEN = datetime(2026, 3, 6, 18, 0, tzinfo=timezone.utc)
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)


def lifts(change) -> dict:
    """The two feeds with the lifts feed changed by ``change``."""
    feed = json.loads(PAGES["lifts"])
    change(feed)
    return {**PAGES, "lifts": json.dumps(feed)}


def snow(**figures) -> dict:
    return {**PAGES, "snow": json.dumps({**json.loads(PAGES["snow"]), **figures})}


def test_each_lift_is_read_with_the_runs_under_it():
    feed = sasquatch.parse(PAGES, THEN)
    assert feed["Name"] == "Sasquatch Mountain" and feed["LastUpdate"] == "2026-03-06T18:00:00Z"
    assert [(area["Name"], area["Lifts"][0]["Status"], len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("Littlefoot Carpet", "Open", 3), ("Whistle Punk Chair", "Open", 2), ("Sasquatch Chair", "Closed", 10),
        ("Yeti Chair", "Open", 22)]
    # "closed: 🔴 Closed" is the word before the colon.
    assert feed["MountainAreas"][2]["Lifts"] == [{"Name": "Sasquatch Chair", "Status": "Closed",
                                                  "StatusEnglish": "closed", "Difficulty": None}]
    trails = {trail["Name"]: trail for area in feed["MountainAreas"] for trail in area["Trails"]}
    assert len(trails) == 37
    assert sum(trail["StatusEnglish"] == "open" for trail in trails.values()) == 25
    # A run's difficulty is the symbol its name starts with; a terrain park without one has none.
    assert trails["Chaser"] == {"Name": "Chaser", "Status": "Open", "StatusEnglish": "open", "Difficulty": "Green",
                                "Grooming": "Yes"}
    assert trails["Snag's"] == {"Name": "Snag's", "Status": "Closed", "StatusEnglish": "closed",
                                "Difficulty": "Blue", "Grooming": "No"}
    assert trails["Fall Away"]["Difficulty"] == "Black" and trails["Mini Terrain Park"]["Difficulty"] == ""
    assert trails["Hemmy Terrain Park"]["Difficulty"] == "Blue"
    assert {trail["Difficulty"] for trail in trails.values()} == {"Green", "Blue", "Black", ""}


def test_the_snow_report_gives_the_alpine_plot_in_inches_and_when_it_was_written():
    report = sasquatch.parse(PAGES, THEN)["SnowReport"]
    # "29/03/2026 9:27 am" in Vancouver; 205 cm is 80.7 inches; the 48 hour and season figures are dashes.
    assert report["LastUpdate"] == "2026-03-29T16:27:00Z" and report["Resortwide"] is True
    assert report["BaseArea"] == {"Name": "Alpine", "BaseIn": 80.7, "Last12HoursIn": 0.0, "Last24HoursIn": 0.0}
    assert report["SeasonTotalIn"] is None and report["BaseConditions"] is None
    filled = sasquatch.parse(snow(past24="13", past48="20.5", season_total="762"), THEN)["SnowReport"]
    assert filled["BaseArea"]["Last24HoursIn"] == 5.1 and filled["BaseArea"]["Last48HoursIn"] == 8.1
    assert filled["SeasonTotalIn"] == 300.0


def test_last_season_s_statuses_with_lifts_open_are_refused():
    with pytest.raises(ValueError, match="last changed 2026-03-06 and have lifts or runs open"):
        sasquatch.parse(PAGES, NOW)

    def close(feed):
        for lift in feed["lifts"]:
            lift["lift_status"] = "closed"
            for run in lift["runs"]:
                run["run_status"] = "closed"

    # The same statuses with everything closed are a closed mountain, whatever their age.
    feed = sasquatch.parse(lifts(close), NOW)
    rows = [row for area in feed["MountainAreas"] for row in area["Lifts"] + area["Trails"]]
    assert len(rows) == 41 and {row["StatusEnglish"] for row in rows} == {"closed"}


def test_another_status_is_carried_in_the_feed_s_words():
    def hold(feed):
        feed["lifts"][3]["lift_status"] = "marginal: 🟡 Marginal"
        feed["lifts"][3]["runs"][0]["run_status"] = "Wind Hold"
        feed["lifts"][3]["runs"][1]["run_name"] = "◆◆ Ridgeview"

    area = sasquatch.parse(lifts(hold), THEN)["MountainAreas"][3]
    assert (area["Lifts"][0]["Status"], area["Lifts"][0]["StatusEnglish"]) == ("Marginal", "marginal")
    assert (area["Trails"][0]["Status"], area["Trails"][0]["StatusEnglish"]) == ("Wind hold", "wind hold")
    assert area["Trails"][1]["Name"] == "Ridgeview" and area["Trails"][1]["Difficulty"] == "Double black"


def test_a_feed_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="lists no lifts"):
        sasquatch.parse(lifts(lambda feed: feed.update(lifts=[])), THEN)
    with pytest.raises(ValueError, match="lists no lifts"):
        sasquatch.parse({**PAGES, "lifts": "[]"}, THEN)
    with pytest.raises(ValueError, match="which is not a word"):
        sasquatch.parse(lifts(lambda feed: feed["lifts"][0].update(lift_status="")), THEN)
    with pytest.raises(ValueError, match="which is not a word"):
        sasquatch.parse(lifts(lambda feed: feed["lifts"][0]["runs"][0].update(run_status=3)), THEN)
    with pytest.raises(ValueError, match="symbol the reader does not know"):
        sasquatch.parse(lifts(lambda feed: feed["lifts"][0]["runs"][0].update(run_name="🟧 Chaser")), THEN)
    with pytest.raises(ValueError, match="does not say whether it is groomed"):
        sasquatch.parse(lifts(lambda feed: feed["lifts"][0]["runs"][0].pop("groomed")), THEN)
    with pytest.raises(ValueError, match="no name or no list of runs"):
        sasquatch.parse(lifts(lambda feed: feed["lifts"][0].pop("runs")), THEN)
    with pytest.raises(ValueError, match="lists a lift twice"):
        sasquatch.parse(lifts(lambda feed: feed["lifts"][1].update(lift_name="Yeti Chair")), THEN)
    with pytest.raises(ValueError, match="not a day and a time"):
        sasquatch.parse(lifts(lambda feed: feed.update(status_updated="yesterday")), THEN)
    with pytest.raises(ValueError):
        sasquatch.parse({**PAGES, "lifts": "<html><body>Not the feed</body></html>"}, THEN)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = sasquatch.parse(snow(alpine_base="deep"), THEN)
    assert "SnowReport" not in feed and len(feed["MountainAreas"]) == 4
    assert "SnowReport" not in sasquatch.parse(snow(date_updated="March 29"), THEN)
    assert "SnowReport" not in sasquatch.parse(snow(alpine_base="-", past24="-"), THEN)
    assert "SnowReport" not in sasquatch.parse({**PAGES, "snow": "{}"}, THEN)
    assert "SnowReport" not in sasquatch.parse({**PAGES, "snow": "<html>"}, THEN)
