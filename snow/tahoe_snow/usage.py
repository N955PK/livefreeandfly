"""How much of Open-Meteo's free allowance the forecast runs use.

The service publishes no quota counter, so each run adds up its own requests by the service's counting rule and
keeps a month of run totals beside the forecast archive.
"""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tahoe_snow.config import DATA
from tahoe_snow.sources import openmeteo

LEDGER = DATA / "archive" / "usage.json"
KEEP_DAYS = 31
STAMP = "%Y-%m-%dT%H:%M:%SZ"


def of_run(requests: list) -> dict:
    """Totals for one run from the cache module's request log."""
    ours = [(url, params, outcome) for url, params, outcome in requests if "open-meteo.com" in url]
    served = [(url, params) for url, params, outcome in ours if outcome == "ok"]
    calls = sum(openmeteo.call_weight(url, params or {}) for url, params in served)
    return {"requests": len(served), "calls": round(calls, 1),
            "rate_limited": sum(outcome == "limited" for _, _, outcome in ours)}


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
