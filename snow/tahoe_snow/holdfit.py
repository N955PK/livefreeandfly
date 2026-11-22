"""What wind has actually put lifts on hold, read off the record that holds.py keeps.

For each mountain in the record, the rows are sorted into bands of summit gust (the stronger of the forecast's and
the resort's own station's), and each band says how often a lift was on a wind hold and what share of the running
lifts were held. From bands with enough in them it proposes the three gust levels the page's outlook uses: holds
possible, holds likely, and closures. A band, and so a proposal, counts only once it has rows from several days:
one windy afternoon is not a rule.

Only holds the resort itself blames on wind count. A lift "Delayed" on a calm morning, or on a patrol hold, is not
a wind hold, and the record so far is mostly those.
python -m tahoe_snow.holdfit holds.jsonl [out.json]
"""
import json
import re
import sys
from collections import defaultdict

BANDS = (0, 20, 30, 40, 50, 60, 200)  # mph of summit gust; the last edge is only a ceiling
MIN_ROWS, MIN_DAYS = 8, 3             # what a band needs before it counts
MIN_RUNNING = 3                       # lifts open or held; fewer and the mountain is barely running
# The level is the lowest band where this holds: (share of rows with any wind hold, mean share of lifts held).
LEVELS = {"possible": (0.25, 0.0), "likely": (0.5, 0.25), "shut": (0.75, 0.6)}


def load(path: str) -> list[dict]:
    with open(path) as handle:
        return [json.loads(line) for line in handle if line.strip()]


def strongest(row: dict, forecast: str, live: str) -> float | None:
    """The stronger of the forecast's and the station's figure; None when the row has neither."""
    found = [value for value in (row.get(forecast), row.get(live)) if isinstance(value, (int, float))]
    return max(found) if found else None


def wind_held(row: dict) -> int:
    """How many of the row's held lifts the resort blames on wind."""
    return sum(1 for words in (row.get("held") or {}).values() if re.search("wind", words or "", re.I))


def band_of(gust: float) -> tuple[int, int]:
    return next((low, high) for low, high in zip(BANDS, BANDS[1:]) if low <= gust < high)


def bands(rows: list[dict]) -> dict:
    """One mountain's rows by gust band: how many rows and days, how often wind held a lift, and how much of the hill."""
    found = defaultdict(lambda: {"rows": 0, "days": set(), "with_hold": 0, "share": 0.0})
    for row in rows:
        gust, running = strongest(row, "gust_mph", "live_gust_mph"), row.get("open", 0) + row.get("hold", 0)
        if gust is None or running < MIN_RUNNING:
            continue
        held, band = wind_held(row), found[band_of(gust)]
        band["rows"] += 1
        band["days"].add(row["utc"][:10])
        band["with_hold"] += held > 0
        band["share"] += held / running
    return {edges: {"rows": b["rows"], "days": len(b["days"]), "any_hold": b["with_hold"] / b["rows"],
                    "held_share": b["share"] / b["rows"], "enough": b["rows"] >= MIN_ROWS and len(b["days"]) >= MIN_DAYS}
            for edges, b in sorted(found.items())}


def proposal(found: dict) -> dict:
    """The gust (mph) for each level: the foot of the lowest band with enough rows that meets it. None where the
    record cannot say yet."""
    out = {}
    for level, (any_hold, held_share) in LEVELS.items():
        out[level] = next((low for (low, _), band in found.items()
                           if band["enough"] and band["any_hold"] >= any_hold and band["held_share"] >= held_share), None)
    return out


def summary(rows: list[dict]) -> dict:
    by_mountain = defaultdict(list)
    for row in rows:
        by_mountain[row["resort"]].append(row)
    out = {}
    for key, mine in sorted(by_mountain.items()):
        found = bands(mine)
        out[key] = {"rows": len(mine), "days": len({row["utc"][:10] for row in mine}),
                    "wind_hold_rows": sum(1 for row in mine if wind_held(row)),
                    "other_hold_rows": sum(1 for row in mine if row.get("hold") and not wind_held(row)),
                    "bands": {f"{low}-{high}": band for (low, high), band in found.items()}, "propose": proposal(found)}
    return out


def report(found: dict) -> str:
    lines = []
    for key, mountain in found.items():
        lines.append(f"{key}: {mountain['rows']} rows on {mountain['days']} days; a wind hold in {mountain['wind_hold_rows']}, "
                     f"some other hold or delay in {mountain['other_hold_rows']}")
        for name, band in mountain["bands"].items():
            lines.append(f"  gusts {name:>7} mph: {band['rows']:3d} rows, {band['days']} days, wind hold in {band['any_hold']:.0%}, "
                         f"{band['held_share']:.0%} of lifts held{'' if band['enough'] else '  (too few to count)'}")
        said = ", ".join(f"{level} at {gust} mph" for level, gust in mountain["propose"].items() if gust is not None)
        lines.append(f"  proposes: {said or 'nothing yet; no band has enough windy rows with wind holds'}")
    return "\n".join(lines)


def main(path: str, out: str | None = None) -> int:
    found = summary(load(path))
    print(report(found))
    if out:
        with open(out, "w") as handle:
            json.dump(found, handle, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
