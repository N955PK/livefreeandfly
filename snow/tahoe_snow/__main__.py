"""Command line: python -m tahoe_snow run | prune."""
import argparse
import sys
from datetime import datetime, timedelta, timezone

from tahoe_snow import pipeline
from tahoe_snow.config import DATA

ARCHIVE_DAYS = 21


def prune(days: int) -> int:
    """Delete archived forecasts older than ``days`` (their forecasts have all come due and been graded)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    removed = 0
    for path in (DATA / "archive").glob("*/*/*.json"):
        year, month = path.parts[-3], path.parts[-2]
        day, hour = path.stem.rstrip("z").split("_")
        if datetime(int(year), int(month), int(day), int(hour), tzinfo=timezone.utc) < cutoff:
            path.unlink()
            removed += 1
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(prog="tahoe_snow")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run", help="fetch, forecast, and write the site's data files")
    sub.add_parser("prune", help="delete archived forecasts that are no longer needed").add_argument(
        "--days", type=int, default=ARCHIVE_DAYS)
    args = parser.parse_args()
    if args.command == "run":
        pipeline.run()
    else:
        print(f"removed {prune(args.days)} archived forecasts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
