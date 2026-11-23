"""Command line: python -m tahoe_snow run [region] | due | season | prune | usage | budget [region]."""
import argparse
import sys
from datetime import datetime, timedelta, timezone

from tahoe_snow import pipeline, usage
from tahoe_snow.config import DATA, REGIONS

ARCHIVE_DAYS = 21


def prune(days: int) -> int:
    """Delete archived forecasts older than ``days`` (their forecasts have all come due and been graded)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    removed = 0
    for path in (DATA / "archive").glob("*/*/*.json"):
        year, month = path.parts[-3], path.parts[-2]
        # DD_HHz.json before the regions were published apart, DD_HHz_<region>.json since.
        day, hour = path.stem.split("_")[:2]
        hour = hour.rstrip("z")
        if datetime(int(year), int(month), int(day), int(hour), tzinfo=timezone.utc) < cutoff:
            path.unlink()
            removed += 1
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(prog="tahoe_snow")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="fetch, forecast, and write one region's data file (every region by default)")
    run.add_argument("region", nargs="?", choices=list(REGIONS))
    sub.add_parser("due", help="print the region whose forecast is most overdue, or nothing if none is due")
    sub.add_parser("prune", help="delete archived forecasts that are no longer needed").add_argument(
        "--days", type=int, default=ARCHIVE_DAYS)
    sub.add_parser("season", help="refresh the season figures from the snow sensors, leaving the forecast alone")
    sub.add_parser("usage", help="report the Open-Meteo allowance used; exit 1 near the limit").add_argument(
        "--fail-over", type=float, default=0.9)
    budget = sub.add_parser("budget", help="exit 1 if another forecast run does not fit the allowance")
    budget.add_argument("--by-hand", action="store_true", help="hold the run to the stricter rule for runs by hand")
    budget.add_argument("region", nargs="?", choices=list(REGIONS), help="the region about to run (default: largest)")
    args = parser.parse_args()
    if args.command == "run":
        failed = []
        for key in [args.region] if args.region else REGIONS:
            try:
                pipeline.run(key)
            except SystemExit as error:
                failed.append(f"{key}: {error}")
        if failed:
            raise SystemExit("; ".join(failed))
    elif args.command == "due":
        due = pipeline.due()
        if due:
            print(due)
    elif args.command == "season":
        pipeline.refresh_season()
    elif args.command == "usage":
        return usage.check(args.fail_over)
    elif args.command == "budget":
        return usage.gate(args.by_hand, args.region)
    else:
        print(f"removed {prune(args.days)} archived forecasts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
