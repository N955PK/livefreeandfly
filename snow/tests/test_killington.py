import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import killington

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 11, 23, 21, 0, tzinfo=timezone.utc)


def page(name: str) -> str:
    return (FIXTURES / f"{name}.html").read_text()


def test_lifts_and_trails_are_read_by_area_and_the_list_of_all_lifts_is_not_an_area():
    feed = killington.parse("Killington", page("killington"), NOW)
    assert [(area["Name"], len(area["Lifts"]), len(area["Trails"])) for area in feed["MountainAreas"]] == [
        ("North Ridge Area", 1, 7), ("Snowshed", 3, 5)]


def test_open_expected_and_closed_keep_the_words_the_page_sorts_on():
    feed = killington.parse("Killington", page("killington"), NOW)
    ridge, snowshed = feed["MountainAreas"]
    assert ridge["Lifts"] == [{"Name": "North Ridge Quad", "Status": "Expected", "StatusEnglish": "expected", "Difficulty": None}]
    assert {lift["StatusEnglish"] for lift in snowshed["Lifts"]} == {"closed"}
    opened = [trail for trail in ridge["Trails"] if trail["StatusEnglish"] == "open"]
    assert len(opened) == 4 and all(trail["Grooming"] == "Yes" and trail["Difficulty"] == "Blue" for trail in opened)
    assert snowshed["Trails"][0]["Name"] == "Highlander" and snowshed["Trails"][0]["Difficulty"] == "Green"
    assert killington.status_row("Lift", "wind-hold", None)["StatusEnglish"] == "wind hold"


def test_uphill_routes_are_left_out():
    assert "Uphill Travel" not in {area["Name"] for area in killington.parse("Killington", page("killington"), NOW)["MountainAreas"]}


def test_a_closed_mountain_reads_as_every_lift_and_trail_closed():
    feed = killington.parse("Pico", page("pico"), NOW)
    rows = [row for area in feed["MountainAreas"] for row in area["Lifts"] + area["Trails"]]
    assert [area["Name"] for area in feed["MountainAreas"]] == ["Outpost", "Bonanza"]
    assert rows and {row["StatusEnglish"] for row in rows} == {"closed"}


def test_an_area_whose_cards_do_not_match_its_own_count_is_refused():
    broken = page("pico").replace('<span class="meta-pill">Lifts 0/1</span>', '<span class="meta-pill">Lifts 0/4</span>', 1)
    with pytest.raises(ValueError, match="counts"):
        killington.parse("Pico", broken, NOW)


def test_one_resort_that_fails_costs_none_of_the_others(tmp_path, monkeypatch):
    def fetch(url):
        if "pico" in url:
            raise ConnectionError("down")
        return page("killington")

    monkeypatch.setattr(killington, "fetch", fetch)
    out = tmp_path / "killington.json"
    assert killington.main(str(out)) == 0
    assert set(json.loads(out.read_text())["resorts"]) == {"killington"}
