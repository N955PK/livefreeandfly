import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import hudsonbay

# The snow report page as the site gave it on 2026-11-26, nine days before its opening day, cut down to the script
# that carries its records (the records' owner ids removed).
PAGE = (Path(__file__).parent / "fixtures" / "hudsonbay.html").read_text()
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)
OPEN, CLOSE = '<script type="application/json" id="wix-warmup-data">', "</script>"


def changed(change) -> str:
    """The page with its records changed by ``change``."""
    before, rest = PAGE.split(OPEN)
    body, after = rest.split(CLOSE, 1)
    data = json.loads(body)
    change(data["appsWarmupData"]["dataBinding"]["dataStore"]["recordsByCollectionId"])
    return before + OPEN + json.dumps(data) + CLOSE + after


def lift(found: dict, index: int) -> dict:
    return list(found["HBMLiftStatus"].values())[index]


def depth(line: str) -> str:
    return changed(lambda found: next(iter(found["MessageUnderLiftStatus"].values())).update(mountainStatus=line))


def test_the_four_lifts_are_read_in_the_page_s_order():
    feed = hudsonbay.parse(PAGE, NOW)
    assert feed["Name"] == "Hudson Bay Mountain" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    assert len(feed["MountainAreas"]) == 1 and feed["MountainAreas"][0]["Trails"] == []
    assert feed["MountainAreas"][0]["Lifts"] == [
        {"Name": "Panorama T-Bar", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None},
        {"Name": "Skyline Chair Lift", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None},
        {"Name": "Prairie T-Bar", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None},
        {"Name": "Carpet Lift", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}]
    # Before the season the line reads "Alpine Base Depth:" with nothing after it: no snow report.
    assert "SnowReport" not in feed


def test_open_and_standby_are_carried():
    def turn(found):
        lift(found, 0).update(liftStatus1="Open", _updatedDate={"$date": "2026-11-26T16:30:00.000Z"})
        lift(found, 1).update(liftStatus1="On Standby")

    lifts = hudsonbay.parse(changed(turn), NOW)["MountainAreas"][0]["Lifts"]
    assert [(row["Status"], row["StatusEnglish"]) for row in lifts] == [
        ("Open", "open"), ("On hold", "on hold"), ("Closed", "closed"), ("Closed", "closed")]


def test_last_season_s_statuses_with_a_lift_open_are_refused():
    with pytest.raises(ValueError, match="last changed 2026-11-12 and have lifts open"):
        hudsonbay.parse(changed(lambda found: lift(found, 0).update(liftStatus1="Open")),
                        datetime(2026, 12, 5, 18, 0, tzinfo=timezone.utc))
    # The same statuses are fine on the day they were written.
    then = datetime(2026, 11, 12, 20, 0, tzinfo=timezone.utc)
    feed = hudsonbay.parse(changed(lambda found: lift(found, 0).update(liftStatus1="Open")), then)
    assert feed["MountainAreas"][0]["Lifts"][0]["StatusEnglish"] == "open"


def test_the_base_depth_is_read_in_centimetres_and_given_in_inches():
    report = hudsonbay.parse(depth('<p class="font_8">Alpine Base Depth: 120 cm</p>'), NOW)["SnowReport"]
    # 120 cm is 47.2 inches; the line was last changed on November 12.
    assert report["BaseArea"] == {"Name": "Alpine", "BaseIn": 47.2}
    assert report["LastUpdate"] == "2026-11-12T19:12:43Z" and report["Resortwide"] is True
    assert report["SeasonTotalIn"] is None and report["BaseConditions"] is None
    assert hudsonbay.parse(depth("<p>Alpine Base Depth:&nbsp;<strong>95cm</strong></p>"), NOW)["SnowReport"][
        "BaseArea"]["BaseIn"] == 37.4
    assert hudsonbay.parse(depth("<p>Alpine Base Depth: 101.5</p>"), NOW)["SnowReport"]["BaseArea"]["BaseIn"] == 40.0


def test_a_base_depth_that_cannot_be_read_costs_only_the_snow_report():
    for line in ("<p>Alpine Base Depth: lots</p>", "<p>Alpine Base Depth: 48 inches</p>", "<p>See you in December</p>",
                 "<p>Alpine Base Depth: 100-120 cm</p>", ""):
        feed = hudsonbay.parse(depth(line), NOW)
        assert "SnowReport" not in feed and len(feed["MountainAreas"][0]["Lifts"]) == 4
    assert "SnowReport" not in hudsonbay.parse(changed(lambda found: found.pop("MessageUnderLiftStatus")), NOW)


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="does not carry the records"):
        hudsonbay.parse("<html><body>Snow Report</body></html>", NOW)
    with pytest.raises(ValueError, match="not in the shape"):
        hudsonbay.parse(OPEN + '{"appsWarmupData": {}}' + CLOSE, NOW)
    with pytest.raises(ValueError, match="not in the shape"):
        hudsonbay.parse(OPEN + "not json" + CLOSE, NOW)
    with pytest.raises(ValueError, match="lists no lifts"):
        hudsonbay.parse(changed(lambda found: found.update(HBMLiftStatus={})), NOW)
    with pytest.raises(ValueError, match="lists no lifts"):
        hudsonbay.parse(changed(lambda found: found.pop("HBMLiftStatus")), NOW)
    with pytest.raises(ValueError, match="'Wind Hold', which the reader does not know"):
        hudsonbay.parse(changed(lambda found: lift(found, 0).update(liftStatus1="Wind Hold")), NOW)
    with pytest.raises(ValueError, match="which the reader does not know"):
        hudsonbay.parse(changed(lambda found: lift(found, 0).pop("liftStatus1")), NOW)
    with pytest.raises(ValueError, match="a lift has no name"):
        hudsonbay.parse(changed(lambda found: lift(found, 0).update(title_fld=" ")), NOW)
    with pytest.raises(ValueError, match="lists a lift twice"):
        hudsonbay.parse(changed(lambda found: lift(found, 1).update(title_fld="Panorama T-Bar")), NOW)
    with pytest.raises(ValueError, match="not a day and a time"):
        hudsonbay.parse(changed(lambda found: lift(found, 0).pop("_updatedDate")), NOW)
