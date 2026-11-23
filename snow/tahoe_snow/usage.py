"""How much of Open-Meteo's free allowance the forecast runs use.

The service stamps each response with what it charged for the request, so each run adds those up and keeps a month
of run totals beside the forecast archive. A response without the stamp is counted by the service's published rule.
"""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tahoe_snow.config import DATA, REGIONS, RESORTS
from tahoe_snow.sources import openmeteo

LEDGER = DATA / "archive" / "usage.json"
KEEP_DAYS = 31
STAMP = "%Y-%m-%dT%H:%M:%SZ"
# What a run is taken to cost when the ledger has no runs to go by.
TYPICAL_RUN_CALLS = 1000
# A run started by hand has to leave this much of the day's allowance for the scheduled ones.
BY_HAND_SHARE = 0.9
# What one mountain's forecast costs the service, as the ledger measured it (1,089 calls a run for 21 mountains).
CALLS_PER_RESORT_RUN = 51.9
# The most calls a day the service's plan allows.
PLAN_LIMIT = 8500


def planned(regions: dict = REGIONS, resorts: dict = RESORTS) -> float:
    """Calls a day the configured regions will spend: each mountain's cost for every run its region makes."""
    return sum(sum(r.region == region.key for r in resorts.values()) * 24 / region.every_h * CALLS_PER_RESORT_RUN
               for region in regions.values())


def of_run(requests: list) -> dict:
    """Totals for one run from the cache module's request log."""
    ours = [row for row in requests if "open-meteo.com" in row[0]]
    served = [(url, params, cost) for url, params, outcome, cost in ours if outcome == "ok"]
    by_rule = [openmeteo.call_weight(url, params or {}) for url, params, _ in served]
    calls = sum(rule if cost is None else cost for rule, (_, _, cost) in zip(by_rule, served))
    return {"requests": len(served), "calls": round(calls, 1), "by_rule": round(sum(by_rule), 1),
            "measured": all(cost is not None for _, _, cost in served),
            "rate_limited": sum(row[2] == "limited" for row in ours)}


def record(run: dict, now: datetime, path: Path = LEDGER) -> list:
    """Append a run to the ledger, drop runs older than a month, and return the ledger."""
    ledger = json.loads(path.read_text()) if path.exists() else []
    ledger.append({"utc": now.strftime(STAMP), **run})
    cutoff = (now - timedelta(days=KEEP_DAYS)).strftime(STAMP)
    ledger = [row for row in ledger if row["utc"] >= cutoff]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, separators=(",", ":")))
    return ledger


def summary(ledger: list, now: datetime) -> dict:
    """Calls in the last 24 hours and 30 days against the free limits."""
    def since(days: float) -> list:
        cutoff = (now - timedelta(days=days)).strftime(STAMP)
        return [row for row in ledger if row["utc"] > cutoff]

    day, month = since(1), since(30)
    return {"calls_24h": round(sum(row["calls"] for row in day)), "runs_24h": len(day),
            "calls_30d": round(sum(row["calls"] for row in month)),
            "rate_limited_24h": sum(row["rate_limited"] for row in day),
            "measured": bool(day) and all(row.get("measured") for row in day),
            "daily_limit": openmeteo.DAILY_CALLS, "monthly_limit": openmeteo.MONTHLY_CALLS}


def check(fail_over: float, path: Path = LEDGER) -> int:
    """Print the budget, add it to the GitHub job summary, and return 1 when it is past ``fail_over`` of a limit
    or the service has refused requests."""
    if not path.exists():
        print("no usage recorded yet")
        return 0
    use = summary(json.loads(path.read_text()), datetime.now(timezone.utc))
    day, month = use["calls_24h"] / use["daily_limit"], use["calls_30d"] / use["monthly_limit"]
    lines = [f"Open-Meteo calls, last 24 hours: {use['calls_24h']:,} of {use['daily_limit']:,} ({day:.0%}) "
             f"in {use['runs_24h']} runs",
             f"Open-Meteo calls, last 30 days: {use['calls_30d']:,} of {use['monthly_limit']:,} ({month:.0%})",
             f"Requests refused for rate limiting, last 24 hours: {use['rate_limited_24h']}"]
    print("\n".join(lines))
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as out:
            out.write("### Data budget\n\n" + "\n".join(f"- {line}" for line in lines) + "\n")
    over = max(day, month) > fail_over or use["rate_limited_24h"] > 0
    if over:
        print(f"::error::The forecast is using more than {fail_over:.0%} of the Open-Meteo free allowance, "
              "or was rate limited.")
    return int(over)


def room(ledger: list, now: datetime, by_hand: bool) -> tuple:
    """Whether another forecast run fits the day's allowance, and a line saying why.

    A scheduled run goes ahead until the service has actually refused requests; the ledger's rolling day is
    stricter than however the service counts, and a forecast is worth more than the margin. Once it has been
    refused, runs wait until the ledger shows a run's worth of room. A run started by hand always has to fit,
    with room left over."""
    use = summary(ledger, now)
    recent = [row["calls"] for row in ledger[-3:]]
    next_run = sum(recent) / len(recent) if recent else TYPICAL_RUN_CALLS
    limit = use["daily_limit"] * (BY_HAND_SHARE if by_hand else 1.0)
    fits = use["calls_24h"] + next_run <= limit
    told = (f"{use['calls_24h']:,} calls in the last 24 hours, about {next_run:,.0f} more for this run, "
            f"limit {limit:,.0f}")
    if fits:
        return True, f"Room for a run: {told}."
    if not by_hand and use["rate_limited_24h"] == 0:
        return True, f"Over the ledger's count but nothing has been refused, so the run goes ahead: {told}."
    return False, f"No room for a run: {told}."


def gate(by_hand: bool, path: Path = LEDGER) -> int:
    """Print whether a run should go ahead and return 0 if so, 1 to skip it."""
    ledger = json.loads(path.read_text()) if path.exists() else []
    go, why = room(ledger, datetime.now(timezone.utc), by_hand)
    print(why)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as out:
            out.write(f"### Data budget\n\n{why}\n")
    return 0 if go else 1
