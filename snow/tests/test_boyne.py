import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import boyne

LOON = Path(__file__).parent / "fixtures" / "boyne_loon.json"
NOW = datetime(2026, 11, 23, 21, 0, tzinfo=timezone.utc)


def loon() -> dict:
    return json.loads(LOON.read_text())


def test_the_three_resorts_are_read_from_their_own_sites_by_the_code_each_page_names():
    assert {key: spec[1:] for key, spec in boyne.RESORTS.items()} == {
        "sugarloaf": ("www.sugarloaf.com", "sl"), "sundayriver": ("www.sundayriver.com", "sr"), "loon": ("www.loonmtn.com", "lm")}


def test_a_closed_mountain_reads_as_every_lift_and_trail_closed_by_area():
    # Loon's report the week before it opened: every lift closed, the Nordic trails open.
    feed = boyne.parse("Loon", loon(), NOW)
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("North Peak", 1, 2), ("South Peak", 4, 2), ("West Basin", 5, 2), ("Loon Peak", 3, 2)]
    rows = [row for area in feed["MountainAreas"] for row in area["Lifts"] + area["Trails"]]
    assert {row["StatusEnglish"] for row in rows} == {"closed"} and all(row["Name"] for row in rows)


def test_nordic_and_uphill_routes_are_not_counted_as_the_mountain_s_trails():
    names = {area["Name"] for area in boyne.parse("Loon", loon(), NOW)["MountainAreas"]}
    assert "Nordic" not in names and "Uphill Routes" not in names


def test_statuses_difficulty_and_grooming_take_the_words_the_page_reads():
    assert boyne.status_row("Lift", "On Hold", None)["StatusEnglish"] == "on hold"
    assert boyne.status_row("Lift", "Open", None)["Status"] == "Open"
    trail = boyne.trail_row({"name": "Run", "status": "Open", "difficultyIcon": "expert", "groomed": True})
    assert trail == {"Name": "Run", "Status": "Open", "StatusEnglish": "open", "Difficulty": "Double black", "Grooming": "Yes"}


def test_a_report_whose_lifts_do_not_add_up_is_refused():
    report = loon()
    report["currentConditions"]["resortwide"]["numLiftsTotal"] += 1
    with pytest.raises(ValueError, match="counts 14 lifts but 13"):
        boyne.parse("Loon", report, NOW)


def test_one_resort_that_fails_costs_none_of_the_others(tmp_path, monkeypatch):
    def fetch(host, code):
        if code != "lm":
            raise ConnectionError("down")
        return loon()

    monkeypatch.setattr(boyne, "fetch", fetch)
    out = tmp_path / "boyne.json"
    assert boyne.main(str(out)) == 0
    assert set(json.loads(out.read_text())["resorts"]) == {"loon"}


SUGARLOAF_OLD = Path(__file__).parent / "fixtures" / "boyne_sugarloaf_old.json"


def test_the_snow_report_is_carried_in_the_ikon_feed_s_shape_with_the_resort_s_own_time():
    # Loon's report on 2026-11-23, the week before it opened: every figure posted as 0, two left empty.
    snow = boyne.parse("Loon", loon(), NOW)["SnowReport"]
    assert snow["LastUpdate"] == "2026-11-23T17:48:15Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": 0, "BaseMinIn": 0, "BaseMaxIn": 0, "Last24HoursIn": 0,
                                "Last48HoursIn": None, "Last72HoursIn": None, "Last7DaysIn": 0}
    assert snow["BaseConditions"] is None and snow["SeasonTotalIn"] == 0
    assert snow["Report"].startswith("<p>Colder temperatures are making a return")


def test_an_old_report_keeps_the_time_it_was_posted_not_the_time_it_was_read():
    # Sugarloaf's report read on the 23rd was last posted on the 19th, with last spring's surface words.
    snow = boyne.parse("Sugarloaf", json.loads(SUGARLOAF_OLD.read_text()), NOW)["SnowReport"]
    assert snow["LastUpdate"] == "2026-11-19T15:48:00Z"
    assert snow["BaseConditions"] == "Spring Conditions, Machine Groomed"
    assert snow["BaseArea"]["Last7DaysIn"] == 7 and snow["SeasonTotalIn"] == 145


def test_figures_the_resort_leaves_empty_stay_empty_and_are_never_made_zero():
    assert boyne.inches(None) is None
    assert boyne.inches({"inches": "", "centimeters": ""}) is None
    assert boyne.inches({"inches": "18", "centimeters": "46"}) == 18
    assert boyne.inches({"inches": "2.5", "centimeters": "6"}) == 2.5
    report = loon()
    report["currentConditions"]["resortLocations"]["location"][0].update(base=None, baseMin=None, baseMax=None)
    area = boyne.parse("Loon", report, NOW)["SnowReport"]["BaseArea"]
    assert (area["BaseIn"], area["BaseMinIn"], area["BaseMaxIn"]) == (None, None, None)


def test_the_nordic_centre_s_figures_are_not_the_mountain_s():
    report = loon()
    report["currentConditions"]["resortLocations"]["location"].reverse()   # Nordic first
    assert boyne.snow_report(report)["BaseArea"]["Last24HoursIn"] == 0
    report["currentConditions"]["resortLocations"]["location"] = report["currentConditions"]["resortLocations"]["location"][:1]
    assert boyne.snow_report(report) is None


def test_the_file_carries_the_snow_report_beside_the_lifts(tmp_path, monkeypatch):
    monkeypatch.setattr(boyne, "fetch", lambda host, code: loon() if code == "lm" else json.loads(SUGARLOAF_OLD.read_text()))
    monkeypatch.setitem(boyne.RESORTS, "sundayriver", ("Sunday River", "www.sundayriver.com", "lm"))
    out = tmp_path / "boyne.json"
    assert boyne.main(str(out)) == 0
    resorts = json.loads(out.read_text())["resorts"]
    assert resorts["sugarloaf"]["SnowReport"]["LastUpdate"] == "2026-11-19T15:48:00Z"
    assert resorts["loon"]["SnowReport"]["BaseArea"]["BaseIn"] == 0
