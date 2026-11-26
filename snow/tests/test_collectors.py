"""Each collector builds, publishes and counts only its own regions."""
import os
import subprocess
import sys

from tahoe_snow import config, usage


def test_this_process_is_the_first_collector_and_sees_only_its_regions():
    assert config.COLLECTOR == "main"
    assert set(config.REGIONS) == {key for key, region in config.ALL_REGIONS.items() if region.collector == "main"}
    assert set(config.RESORTS) == {key for key, resort in config.ALL_RESORTS.items() if resort.region in config.REGIONS}
    assert {"tahoe", "mammoth", "newengland", "seattle"} <= set(config.REGIONS)


def test_every_mountain_belongs_to_a_region_some_collector_builds():
    assert {resort.region for resort in config.ALL_RESORTS.values()} <= set(config.ALL_REGIONS)
    assert all(region.collector in ("main", "canada", "west", "north", "east") for region in config.ALL_REGIONS.values())
    # A region outside the USA says so. Canada's are the second collector's, but for Quebec, which the fifth builds.
    assert {key for key, region in config.ALL_REGIONS.items() if region.country == "Canada"} == {
        key for key, region in config.ALL_REGIONS.items() if region.collector == "canada"} | {"quebec"}
    assert config.ALL_REGIONS["quebec"].collector == "east"


def test_the_second_collector_sees_the_other_share_and_plans_only_that():
    code = ("from tahoe_snow import config, usage; "
            "print(config.COLLECTOR, sorted(config.REGIONS), len(config.RESORTS), round(usage.planned()))")
    out = subprocess.run([sys.executable, "-c", code], env={**os.environ, "SNOW_COLLECTOR": "canada"}, text=True,
                         capture_output=True, check=True).stdout.split(" ", 1)
    assert out[0] == "canada"
    theirs = sorted(key for key, region in config.ALL_REGIONS.items() if region.collector == "canada")
    assert out[1].startswith(str(theirs))
    assert not set(theirs) & set(config.REGIONS)
    # What this collector plans is its own regions' calls alone.
    assert usage.planned() == usage.planned(config.REGIONS, config.RESORTS)
