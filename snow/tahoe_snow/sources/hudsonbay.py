"""Hudson Bay Mountain's lifts, and its alpine base depth, from its snow report page
(hudsonbaymountain.com/snowreport).

The site is built on Wix, and the page carries the records it draws its lift cards from as JSON in a script
("wix-warmup-data"): one record a lift in the "HBMLiftStatus" collection, with the lift's name, its status ("Open",
"Closed" or "On Standby", the three the collection allows; any other fails), and when the record was last changed.
The page lists no runs one by one (a lift's groomed runs are a line of free text), so there are no trails here; its
two other cards, the Rotary Trail to town and the terrain park, are not lifts and are left out.

The resort leaves its last statuses up between seasons. Statuses last changed more than OLD_DAYS ago with a lift
still reading open are refused: they are last season's.

The base depth is one line the resort types under "Mountain Status" ("Alpine Base Depth: 120 cm"), in centimetres,
turned into inches here (divided by 2.54, to one decimal). The line with no figure after it is no snow report, and
a line that cannot be read costs only the snow report, not the lifts. The page gives no new snow: its snow table is
on another site. Standard library only.
"""
import html
import json
import re
from datetime import datetime, timedelta, timezone

URL = "https://www.hudsonbaymountain.com/snowreport"
NAME = "Hudson Bay Mountain"
STAMP = "%Y-%m-%dT%H:%M:%SZ"
CM_PER_INCH = 2.54
# Statuses older than this with a lift open are last season's, left up after the mountain closed.
OLD_DAYS = 14
# The collection's three statuses, as (the words shown, the plain status).
STATUSES = {"open": ("Open", "open"), "closed": ("Closed", "closed"), "on standby": ("On hold", "on hold")}
WARMUP = re.compile(r'<script type="application/json" id="wix-warmup-data">(.*?)</script>', re.S)
TAG = re.compile(r"<[^>]+>")
DEPTH = re.compile(r"alpine base depth\s*:?\s*(.*)", re.I | re.S)
CENTIMETRES = re.compile(r"(\d+(?:\.\d+)?)\s*(?:cm|centimetres|centimeters)?\.?", re.I)


def records(page: str) -> dict:
    """The page's records, by the name of the collection they are from."""
    found = WARMUP.search(page)
    if not found:
        raise ValueError("the page does not carry the records its cards are drawn from")
    try:
        return json.loads(found.group(1))["appsWarmupData"]["dataBinding"]["dataStore"]["recordsByCollectionId"]
    except (ValueError, KeyError, TypeError) as error:
        raise ValueError("the page's records are not in the shape the reader knows") from error


def changed(record: dict, name: str) -> datetime:
    """When a record was last changed."""
    said = (record.get("_updatedDate") or {}).get("$date") if isinstance(record.get("_updatedDate"), dict) else None
    try:
        return datetime.strptime(str(said), "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    except ValueError as error:
        raise ValueError(f"{name} was last changed {said!r}, which is not a day and a time") from error


def lifts(found: dict) -> tuple:
    """The lifts in the page's order, and when the newest of their statuses was written."""
    rows = found.get("HBMLiftStatus")
    if not isinstance(rows, dict) or not rows:
        raise ValueError("the page lists no lifts")
    out, newest = [], None
    for record in rows.values():
        name = " ".join(str(record.get("title_fld") or "").split())
        if not name:
            raise ValueError("a lift has no name")
        said = " ".join(str(record.get("liftStatus1") or "").lower().split())
        if said not in STATUSES:
            raise ValueError(f"{name} has the status {record.get('liftStatus1')!r}, which the reader does not know")
        words, plain = STATUSES[said]
        at = changed(record, name)
        newest = at if newest is None or at > newest else newest
        out.append({"Name": name, "Status": words, "StatusEnglish": plain, "Difficulty": None})
    if len({lift["Name"] for lift in out}) != len(out):
        raise ValueError("the page lists a lift twice")
    return out, newest


def snow_report(found: dict) -> dict:
    """The alpine base depth in the shape of the Ikon feed's SnowReport, centimetres turned into inches."""
    rows = found.get("MessageUnderLiftStatus")
    if not isinstance(rows, dict) or len(rows) != 1:
        raise ValueError("the page has no line under Mountain Status")
    record = next(iter(rows.values()))
    line = " ".join(html.unescape(TAG.sub(" ", str(record.get("mountainStatus") or ""))).split())
    depth = DEPTH.search(line)
    if not depth:
        raise ValueError(f"the line under Mountain Status reads {line!r}, not the alpine base depth")
    said = depth.group(1).strip()
    if not said:
        raise ValueError("the alpine base depth is not filled in")
    figure = CENTIMETRES.fullmatch(said)
    if not figure:
        raise ValueError(f"the alpine base depth reads {said!r}, not centimetres")
    return {"LastUpdate": changed(record, "the base depth").strftime(STAMP), "Resortwide": True,
            "BaseConditions": None, "SeasonTotalIn": None,
            "BaseArea": {"Name": "Alpine", "BaseIn": round(float(figure.group(1)) / CM_PER_INCH, 1)},
            "Report": None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    found = records(page)
    rows, at = lifts(found)
    if now - at > timedelta(days=OLD_DAYS) and any(row["StatusEnglish"] == "open" for row in rows):
        raise ValueError(f"the statuses were last changed {at:%Y-%m-%d} and have lifts open: they are last season's")
    feed = {"Name": NAME, "LastUpdate": now.astimezone(timezone.utc).strftime(STAMP),
            "MountainAreas": [{"Name": NAME, "Lifts": rows, "Trails": []}]}
    try:
        feed["SnowReport"] = snow_report(found)
    except ValueError as error:
        # A base depth that cannot be read costs only the snow report, not the lifts.
        print(f"{NAME}: snow report: {error}")
    return feed
