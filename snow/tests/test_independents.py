"""The runner for the mountains that each have a reader of their own."""
from datetime import datetime, timezone

from tahoe_snow import config
from tahoe_snow.sources import independents

NOW = datetime(2026, 11, 24, 17, 0, tzinfo=timezone.utc)


def feed(open_lifts: int, snow: dict | None) -> dict:
    lifts = [{"Name": f"Chair {n}", "Status": "Open" if n < open_lifts else "Closed",
              "StatusEnglish": "open" if n < open_lifts else "closed", "Difficulty": None} for n in range(3)]
    out = {"Name": "Somewhere", "LastUpdate": "2026-11-24T17:00:00Z",
           "MountainAreas": [{"Name": "Somewhere", "Lifts": lifts, "Trails": []}]}
    if snow is not None:
        out["SnowReport"] = snow
    return out


def test_every_reader_is_a_mountain_of_new_england_the_tetons_the_wasatch_or_colorado_and_says_where_its_page_is():
    for key, module in independents.MODULES.items():
        assert config.RESORTS[key].region in ("newengland", "tetons", "wasatch", "colorado", "shasta"), key
        assert hasattr(module, "URL") or hasattr(module, "URLS"), key
        assert callable(module.parse), key
    assert len(independents.MODULES) == 25
    assert [key for key in independents.MODULES if config.RESORTS[key].region == "shasta"] == ["shastaskipark", "ashland"]
    assert [key for key in independents.MODULES if config.RESORTS[key].region == "colorado"] == ["copper", "loveland"]
    assert [key for key in independents.MODULES if config.RESORTS[key].region == "wasatch"] == [
        "alta", "snowbird", "brighton", "snowbasin", "powdermountain", "sundance"]
    assert [key for key in independents.MODULES if config.RESORTS[key].region == "tetons"] == ["jacksonhole", "targhee"]


def test_a_range_is_given_its_middle_and_a_single_figure_is_left_alone():
    snow = {"LastUpdate": "2026-11-24T12:00:00Z", "Resortwide": True,
            "BaseArea": {"BaseIn": None, "BaseMinIn": 26, "BaseMaxIn": 40, "Last24HoursIn": 3,
                         "Last24HoursMinIn": 2, "Last24HoursMaxIn": 6}}
    area = independents.settled(feed(2, snow), NOW)["SnowReport"]["BaseArea"]
    assert (area["BaseIn"], area["BaseMinIn"], area["BaseMaxIn"]) == (33.0, 26, 40)
    assert area["Last24HoursIn"] == 3
    empty = {"LastUpdate": "2026-11-24T12:00:00Z", "BaseArea": {"BaseIn": None, "BaseMinIn": None, "BaseMaxIn": None}}
    assert independents.settled(feed(2, empty), NOW)["SnowReport"]["BaseArea"]["BaseIn"] is None


def test_a_closed_mountains_undated_or_old_report_is_left_out():
    base = {"BaseArea": {"BaseIn": 25}}
    assert "SnowReport" not in independents.settled(feed(0, {**base, "LastUpdate": None}), NOW)
    assert "SnowReport" not in independents.settled(feed(0, {**base, "LastUpdate": "2026-04-08T12:00:00Z"}), NOW)
    assert "SnowReport" not in independents.settled(feed(0, {**base, "LastUpdate": "last spring"}), NOW)
    # Dated within two weeks, or with a lift turning, it stays.
    assert "SnowReport" in independents.settled(feed(0, {**base, "LastUpdate": "2026-11-16T13:36:00Z"}), NOW)
    assert "SnowReport" in independents.settled(feed(1, {**base, "LastUpdate": None}), NOW)
    assert "SnowReport" not in independents.settled(feed(0, None), NOW)


def test_a_mountain_with_no_lifts_posted_is_left_out():
    empty = {"Name": "Somewhere", "LastUpdate": "2026-11-24T17:00:00Z", "MountainAreas": [{"Name": "Somewhere", "Lifts": [], "Trails": []}]}
    assert not independents.posted(empty)
    assert independents.posted(feed(0, None))
