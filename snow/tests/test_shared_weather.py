"""Mountains a few miles apart are forecast from one request for weather, each read at its own heights."""
import math

import pytest

from tahoe_snow import config, pipeline, usage
from tahoe_snow.config import RESORTS
from tahoe_snow.sources import openmeteo

SHARED = {"pico": "killington", "tuckerman": "wildcat", "mountsnow": "stratton",
          "alpine": "palisades", "boreal": "sugarbowl", "castle": "sugarbowl", "roundtop": "kirkwood",
          "jakes": "tallac", "carsonpeak": "june", "sherwins": "mammoth", "alpental": "snoqualmie",
          "smugglers": "stowe", "bolton": "stowe", "mansfield": "stowe", "madriverglen": "sugarbush",
          "bromley": "stratton", "magic": "stratton", "cannon": "loon", "waterville": "loon",
          "cranmore": "attitash", "blackmountain": "attitash",
          "snowbird": "alta", "superior": "alta", "cardiff": "alta", "solitude": "brighton",
          "deervalley": "parkcity", "timpanogos": "sundance",
          "abasin": "keystone", "lovelandpass": "loveland", "vailpass": "copper", "berthoud": "winterpark"}


def km(a, b) -> float:
    east = math.radians(b.lon - a.lon) * math.cos(math.radians((a.lat + b.lat) / 2))
    return 6371 * math.hypot(east, math.radians(b.lat - a.lat))


def test_the_close_neighbours_share_and_nobody_else_does():
    assert {r.key: r.weather_from for r in RESORTS.values() if r.weather_from} == SHARED


def test_a_mountain_shares_only_with_a_near_neighbour_that_asks_for_its_own():
    for key, neighbour in SHARED.items():
        mine, theirs = RESORTS[key], RESORTS[neighbour]
        assert theirs.weather_from is None and theirs.region == mine.region
        assert km(mine, theirs) < 20, key
        assert config.weather_point(mine) is theirs and config.weather_point(theirs) is theirs


def asked(monkeypatch, key: str) -> tuple:
    """What a mountain's forecast asks the service for, stopping before anything is made of the answer."""
    calls = []

    def forecast(lat, lon, elevation_m, models, variables, **kw):
        calls.append((lat, lon, elevation_m, tuple(models), tuple(variables), tuple(sorted(kw.items()))))
        return {}

    monkeypatch.setattr(openmeteo, "forecast", forecast)
    with pytest.raises(RuntimeError, match="no usable model"):
        pipeline.resort_forecast(RESORTS[key], None, None, pipeline.pd.Timestamp("2026-12-01 12:00"), {})
    return calls[0]


def test_both_of_a_pair_ask_for_exactly_the_same_weather(monkeypatch):
    for key, neighbour in SHARED.items():
        assert asked(monkeypatch, key) == asked(monkeypatch, neighbour), key
    assert asked(monkeypatch, "wildcat")[:3] == (RESORTS["wildcat"].lat, RESORTS["wildcat"].lon,
                                                 RESORTS["wildcat"].summit_m)
    assert asked(monkeypatch, "loon") != asked(monkeypatch, "wildcat")


class Answered(dict):
    """Stands in for a model's weather: it has precipitation, which is all that is looked at before the stubs."""
    def notna(self):
        return self

    def sum(self):
        return 1


class Stopped(Exception):
    pass


def stop(*args, **kw):
    """Ends a forecast once everything has been asked for."""
    raise Stopped


def test_the_members_are_asked_for_at_the_height_their_parents_were(monkeypatch):
    heights = {}

    def forecast(lat, lon, elevation_m, models, variables, **kw):
        heights["parents"] = elevation_m
        return {"gfs_seamless": {"precipitation": Answered()}}

    def ensemble(lat, lon, elevation_m, model, variables, **kw):
        heights[model] = elevation_m
        raise RuntimeError("no members")

    monkeypatch.setattr(openmeteo, "forecast", forecast)
    monkeypatch.setattr(openmeteo, "ensemble", ensemble)
    monkeypatch.setattr(pipeline, "model_snow", lambda *a, **kw: {"made": True})
    monkeypatch.setattr(pipeline, "observed", stop)
    with pytest.raises(Stopped):
        pipeline.resort_forecast(RESORTS["palisades"], None, None, pipeline.pd.Timestamp("2026-12-01 12:00"), {})
    assert "gfs025" in heights and set(heights.values()) == {RESORTS["palisades"].summit_m}


def test_a_shared_mountain_costs_no_calls():
    newengland = {"newengland": config.REGIONS["newengland"]}
    assert usage.pulls("newengland") == len(config.resorts_in("newengland")) - 13 == 16
    assert round(usage.planned(newengland)) == round(16 * 2 * usage.resort_run_calls("newengland"))
    assert usage.estimate([], "newengland") == round(16 * usage.resort_run_calls("newengland"), 1)
    assert (usage.pulls("tahoe"), usage.pulls("mammoth"), usage.pulls("seattle")) == (9, 5, 12)
