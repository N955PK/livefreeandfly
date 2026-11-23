import pandas as pd

from tahoe_snow import config, pipeline, usage


def test_every_resort_belongs_to_a_configured_region():
    assert {r.region for r in config.RESORTS.values()} <= set(config.REGIONS)


def test_the_configured_regions_fit_the_daily_allowance():
    assert usage.planned() <= usage.PLAN_LIMIT


def test_the_home_regions_cost_what_the_ledger_measured():
    # 21 mountains, 4 runs a day, 1,089 calls a run
    home = {key: config.REGIONS[key] for key in ("tahoe", "mammoth")}
    assert round(usage.planned(home)) == round(21 * 4 * 51.9)


def test_avalanche_centers_come_from_the_regions_without_repeats():
    assert config.avalanche_centers() == ("SAC", "ESAC", "BAC")


def test_a_day_is_the_mountains_own_day():
    hours = pd.date_range("2026-12-01 03:00", periods=4, freq="h")       # UTC
    assert list(pipeline.local_days(hours, "America/Los_Angeles").strftime("%Y-%m-%d")) == ["2026-11-30"] * 4
    assert list(pipeline.local_days(hours, "America/New_York").strftime("%Y-%m-%d")) == ["2026-11-30", "2026-11-30", "2026-12-01", "2026-12-01"]
