"""Say when a collector has stopped: a region never published, a forecast long overdue, or lift status gone stale.

Nothing else tells Sean that a collector's chain of runs has broken, or that one region has stopped building, until
the page looks wrong. This reads what each collector has published, as the page does, and fails with one line for
each thing that is late. The workflow that runs it hourly (snow-watch.yml) fails with it, and GitHub's mail about a
failed scheduled run is the alert.

It reads only the published files and the list of regions, and never asks a weather service for anything. Standard
library only.
python -m tools.watch    (from the snow folder)
"""
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

from tahoe_snow.config import ALL_REGIONS

PUBLISHED = "https://raw.githubusercontent.com/N955PK/livefreeandfly"
# The first collector's data branch, as the page names it (DATA_BRANCH); each other collector's ends in its name.
DATA_BRANCH = "snow-data"
LIFT_BRANCH = "snow-lifts"
# The lift files the first collector rewrites on every pass, so their age is the age of its last pass.
LIFT_FILES = ("independents.json", "resort_status.json")
# A pass comes every five minutes by day and every fifteen overnight, so half an hour is at least one pass missed.
LIFTS_LATE_MIN = 30
# A forecast is late once it is older than twice its region's interval and this much more: one build missed outright,
# with room for the build after it to be published.
GRACE_H = 1
STAMP = "%Y-%m-%dT%H:%M:%SZ"
TIMEOUT = 20
TRIES = 3


def branch_of(collector: str) -> str:
    """The branch a collector publishes its regions' forecasts and its index on."""
    return DATA_BRANCH if collector == "main" else f"{DATA_BRANCH}-{collector}"


def data_branches(regions: dict = ALL_REGIONS) -> dict:
    """Every data branch with the regions whose forecasts it should hold, as the configuration has them."""
    out = {}
    for key, region in regions.items():
        out.setdefault(branch_of(region.collector), []).append(key)
    return out


def age(stamp, now: datetime) -> timedelta | None:
    """How long ago a published time was, or None when it is not a time this can read."""
    try:
        return now - datetime.strptime(stamp, STAMP).replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def forecast_problems(indexes: dict, now: datetime, regions: dict = ALL_REGIONS) -> list:
    """A line for each region whose forecast has never been published or is late, going by each collector's index.

    ``indexes`` holds each data branch's ``index.json``, or the reason it could not be read, which is a problem of
    its own: with no index the page has none of that collector's regions."""
    problems = []
    for branch, keys in data_branches(regions).items():
        index = indexes.get(branch)
        if not isinstance(index, dict) or not isinstance(index.get("regions"), dict):
            problems.append(f"{branch}: its index could not be read ({index if index is not None else 'not fetched'}),"
                            f" so nothing is known of {', '.join(keys)}")
            continue
        for key in keys:
            region, entry = regions[key], index["regions"].get(key) or {}
            published = entry.get("published_utc")
            if not published:
                problems.append(f"{region.name} ({key}, {branch}): its forecast has never been published")
                continue
            old, limit = age(published, now), timedelta(hours=2 * region.every_h + GRACE_H)
            if old is None:
                problems.append(f"{region.name} ({key}, {branch}): its published time cannot be read ({published})")
            elif old > limit:
                problems.append(f"{region.name} ({key}, {branch}): its forecast is {old / timedelta(hours=1):.1f} "
                                f"hours old (published {published}); it is built every {region.every_h} hours and is "
                                f"late after {limit / timedelta(hours=1):.0f}")
    return problems


def lift_problems(files: dict, now: datetime) -> list:
    """A line for each lift file that is more than ``LIFTS_LATE_MIN`` old or could not be read. ``files`` holds each
    file as published, or the reason it could not be read."""
    problems = []
    for name in LIFT_FILES:
        document = files.get(name)
        if not isinstance(document, dict):
            problems.append(f"Lift status ({name}, {LIFT_BRANCH}): it could not be read "
                            f"({document if document is not None else 'not fetched'})")
            continue
        old = age(document.get("updated"), now)
        if old is None:
            problems.append(f"Lift status ({name}, {LIFT_BRANCH}): its time cannot be read ({document.get('updated')})")
        elif old > timedelta(minutes=LIFTS_LATE_MIN):
            problems.append(f"Lift status ({name}, {LIFT_BRANCH}): it is {old / timedelta(minutes=1):.0f} minutes old "
                            f"(updated {document['updated']}); the first collector rewrites it every pass and it is "
                            f"late after {LIFTS_LATE_MIN}")
    return problems


def fetch(branch: str, name: str):
    """A published file, or a short reason it could not be read. It is asked for a few times, since one refused
    request would otherwise raise a false alarm."""
    reason = "not read"
    for attempt in range(TRIES):
        try:
            request = urllib.request.Request(f"{PUBLISHED}/{branch}/{name}", headers={"User-Agent": "sierra-snow"})
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as error:
            reason = f"{type(error).__name__}: {error}"
            if attempt + 1 < TRIES:
                time.sleep(5)
    return reason


def report(problems: list) -> int:
    """Print the problems one to a line, put them in the GitHub job summary, and return 1 if there are any."""
    for line in problems:
        print(line)
    if not problems:
        print("Every region's forecast and the lift status are up to date.")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as out:
            if problems:
                out.write("### Late or missing\n\n" + "\n".join(f"- {line}" for line in problems) + "\n")
            else:
                out.write("### Nothing is late\n\nEvery region's forecast and the lift status are up to date.\n")
    if problems and os.environ.get("GITHUB_ACTIONS"):
        # The annotation is what shows on the run's page and in the list of runs.
        print(f"::error::{len(problems)} late or missing: " + "; ".join(problems))
    return int(bool(problems))


def main() -> int:
    indexes = {branch: fetch(branch, "index.json") for branch in data_branches()}
    files = {name: fetch(LIFT_BRANCH, name) for name in LIFT_FILES}
    # The clock is read after the files, so the time spent fetching cannot make a file look newer than it is.
    now = datetime.now(timezone.utc)
    return report(forecast_problems(indexes, now) + lift_problems(files, now))


if __name__ == "__main__":
    sys.exit(main())
