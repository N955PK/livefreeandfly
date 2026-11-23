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
