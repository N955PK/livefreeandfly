"""The hourly check that says when a collector has stopped, and the workflows that run it and the tests."""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tahoe_snow import config
from tools import watch

NOW = datetime(2026, 11, 26, 20, 0, tzinfo=timezone.utc)
WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"
BRANCHES = ["snow-data", "snow-data-canada", "snow-data-west", "snow-data-north", "snow-data-east"]


def ago(**length) -> str:
    return (NOW - timedelta(**length)).strftime(watch.STAMP)


def indexes(published: str | None = None, **regions) -> dict:
    """Every collector's index with each region published at ``published`` (just now, by default), but for those
    named, which are published when they say."""
    out = {}
    for branch, keys in watch.data_branches().items():
        out[branch] = {"regions": {key: {"published_utc": regions.get(key, published or ago(minutes=1))}
                                   for key in keys}, "resorts": []}
    return out


def lifts(**minutes) -> dict:
    return {name: {"updated": ago(minutes=minutes.get(name.split(".")[0], 1)), "resorts": {}}
            for name in watch.LIFT_FILES}


def test_every_region_is_looked_for_on_its_own_collectors_branch():
    branches = watch.data_branches()
    assert sorted(branches) == sorted(BRANCHES)
    assert sorted(key for keys in branches.values() for key in keys) == sorted(config.ALL_REGIONS)
    assert "tahoe" in branches["snow-data"] and "quebec" in branches["snow-data-east"]
    assert all(config.ALL_REGIONS[key].collector == "canada" for key in branches["snow-data-canada"])
    # The page reads the same branches, by the same names.
    page = (Path(__file__).resolve().parents[1] / "index.html").read_text()
    assert 'DATA_BRANCH = "snow-data"' in page
    assert all(f'"{branch}"' in page for branch in BRANCHES[1:])


def test_nothing_is_said_while_everything_is_in_date():
    assert watch.forecast_problems(indexes(), NOW) == []
    assert watch.lift_problems(lifts(), NOW) == []


def test_a_region_never_published_is_named_whether_its_time_is_empty_or_it_is_missing_from_the_index():
    found = indexes(tahoe=None)
    del found["snow-data-canada"]["regions"]["okanagan"]
    assert watch.forecast_problems(found, NOW) == [
        "Tahoe (tahoe, snow-data): its forecast has never been published",
        f"{config.ALL_REGIONS['okanagan'].name} (okanagan, snow-data-canada): its forecast has never been published"]


def test_a_forecast_is_late_once_older_than_twice_its_interval_and_an_hour():
    tahoe, newengland = config.ALL_REGIONS["tahoe"], config.ALL_REGIONS["newengland"]
    assert (tahoe.every_h, newengland.every_h) == (8, 12)
    # Seventeen hours for a region built every eight, twenty-five for one built every twelve.
    on_time = indexes(tahoe=ago(hours=17), newengland=ago(hours=25))
    assert watch.forecast_problems(on_time, NOW) == []
    late = indexes(tahoe=ago(hours=17, minutes=6), newengland=ago(hours=30))
    assert watch.forecast_problems(late, NOW) == [
        f"Tahoe (tahoe, snow-data): its forecast is 17.1 hours old (published {ago(hours=17, minutes=6)}); "
        "it is built every 8 hours and is late after 17",
        f"New England (newengland, snow-data): its forecast is 30.0 hours old (published {ago(hours=30)}); "
        "it is built every 12 hours and is late after 25"]
    # A time that cannot be read is a problem too, not a pass.
    assert watch.forecast_problems(indexes(tahoe="yesterday"), NOW) == [
        "Tahoe (tahoe, snow-data): its published time cannot be read (yesterday)"]


def test_an_index_that_could_not_be_read_is_one_problem_naming_its_regions():
    found = indexes()
    found["snow-data-west"] = "HTTPError: HTTP Error 404: Not Found"
    del found["snow-data-north"]
    west, north = (", ".join(watch.data_branches()[branch]) for branch in ("snow-data-west", "snow-data-north"))
    assert watch.forecast_problems(found, NOW) == [
        "snow-data-west: its index could not be read (HTTPError: HTTP Error 404: Not Found), so nothing is known of "
        f"{west}",
        f"snow-data-north: its index could not be read (not fetched), so nothing is known of {north}"]


def test_lift_status_is_late_after_half_an_hour():
    assert watch.lift_problems(lifts(independents=30, resort_status=29), NOW) == []
    assert watch.lift_problems(lifts(independents=31, resort_status=240), NOW) == [
        f"Lift status (independents.json, snow-lifts): it is 31 minutes old (updated {ago(minutes=31)}); "
        "the first collector rewrites it every pass and it is late after 30",
        f"Lift status (resort_status.json, snow-lifts): it is 240 minutes old (updated {ago(minutes=240)}); "
        "the first collector rewrites it every pass and it is late after 30"]
    unread = {"independents.json": {"resorts": {}}, "resort_status.json": "URLError: timed out"}
    assert watch.lift_problems(unread, NOW) == [
        "Lift status (independents.json, snow-lifts): its time cannot be read (None)",
        "Lift status (resort_status.json, snow-lifts): it could not be read (URLError: timed out)"]


def test_the_report_fails_with_a_line_for_each_problem_and_names_them_in_the_job_summary(tmp_path, monkeypatch, capsys):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    assert watch.report(["Tahoe is late", "Lift status is late"]) == 1
    assert capsys.readouterr().out.splitlines() == [
        "Tahoe is late", "Lift status is late", "::error::2 late or missing: Tahoe is late; Lift status is late"]
    assert summary.read_text() == "### Late or missing\n\n- Tahoe is late\n- Lift status is late\n"
    summary.unlink()
    assert watch.report([]) == 0
    assert "::error::" not in capsys.readouterr().out and "Nothing is late" in summary.read_text()


def test_the_whole_check_reads_each_branch_once_and_fails_only_when_something_is_late(monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    now = datetime.now(timezone.utc)
    fresh = (now - timedelta(minutes=2)).strftime(watch.STAMP)
    asked = []

    def fetch(branch, name, stale=()):
        asked.append((branch, name))
        if name != "index.json":
            return {"updated": fresh, "resorts": {}}
        return {"regions": {key: {"published_utc": None if key in stale else fresh}
                            for key in watch.data_branches()[branch]}}

    monkeypatch.setattr(watch, "fetch", fetch)
    assert watch.main() == 0
    assert sorted(asked[:5]) == sorted((branch, "index.json") for branch in BRANCHES)
    assert asked[5:] == [("snow-lifts", "independents.json"), ("snow-lifts", "resort_status.json")]
    monkeypatch.setattr(watch, "fetch", lambda branch, name: fetch(branch, name, stale=("mammoth",)))
    assert watch.main() == 1
    assert capsys.readouterr().out.splitlines()[-1] == (
        f"{config.ALL_REGIONS['mammoth'].name} (mammoth, snow-data): its forecast has never been published")


def test_the_check_loads_nothing_that_asks_a_weather_service():
    code = ("import sys; from tools import watch; "
            "print([name for name in sys.modules "
            "if name.startswith('tahoe_snow') or name in ('pandas', 'numpy', 'requests')])")
    out = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1], text=True,
                         capture_output=True, check=True, env={**os.environ, "PYTHONPATH": "."}).stdout
    assert json.loads(out.replace("'", '"')) == ["tahoe_snow", "tahoe_snow.config"]
    assert "open-meteo" not in Path(watch.__file__).read_text().split('"""', 2)[2].lower()


# ---------- the workflows, which cannot be run from here ----------
def workflow(name: str) -> str:
    return (WORKFLOWS / name).read_text()


def python_version(text: str) -> str:
    return re.search(r'python-version: "([^"]+)"', text).group(1)


def test_the_tests_run_on_main_and_on_pull_requests_with_what_the_collector_installs():
    tests, collect = workflow("snow-tests.yml"), workflow("snow-collect.yml")
    assert python_version(tests) == python_version(collect)
    # What a collector installs, and on top of it what the fitting code and the tests need.
    assert "run: pip install -r snow/requirements.txt -r snow/requirements-dev.txt\n" in tests
    pinned = re.search(r"curl_cffi==[\d.]+", collect).group(0)
    assert pinned in (WORKFLOWS.parent.parent / "snow" / "requirements-dev.txt").read_text().split()
    assert "  push:\n    branches: [main]\n" in tests and '  pull_request:\n    paths:\n      - "snow/**"\n' in tests
    assert "working-directory: snow\n        run: python -m pytest tests -q\n" in tests
    # It only reads: it cannot push, publish or start another workflow.
    assert "permissions:\n  contents: read\n" in tests and "schedule" not in tests


def test_the_watch_runs_hourly_off_the_hour_and_by_hand_and_only_reads():
    text = workflow("snow-watch.yml")
    minute = re.search(r'- cron: "(\d+) \* \* \* \*"', text).group(1)
    taken = {re.search(r'- cron: "(\d+) ', workflow(path.name)).group(1) for path in WORKFLOWS.glob("*-collect*.yml")}
    assert minute != "0" and minute not in taken
    assert "  workflow_dispatch:\n" in text and "permissions:\n  contents: read\n" in text
    assert "working-directory: snow\n        run: python -m tools.watch\n" in text
    # Nothing may swallow the script's failure: the failed run is the alert.
    assert "continue-on-error" not in text and "|| " not in text
    assert python_version(text) == python_version(workflow("snow-collect.yml"))


def test_every_collector_notes_a_failed_build_and_publishes_the_note():
    collectors = sorted(WORKFLOWS.glob("snow-collect*.yml"))
    assert len(collectors) == 5
    for path in collectors:
        text = path.read_text()
        assert 'python3 -m tahoe_snow failed "$region"' in text, path.name
        # A failed run no longer makes every region wait: only the allowance, or nothing to publish, does.
        begins = text.index("The forecast run failed for $region")
        failed = text[begins:text.index('out="$(mktemp -d)"', begins)]
        assert failed.count("tried=$SECONDS") == 1 and 'if [ ! -f "$code/data/index.json" ]' in failed, path.name
        assert 'cp -r "$code/data/archive" "$out/archive"' in text, path.name
