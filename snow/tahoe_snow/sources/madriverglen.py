"""Mad River Glen's lifts and trails, and its snowfall, from its conditions page (madriverglen.com/conditions/).

The page is built on the server. It lists the lifts in one table, then the trails in one table under each chair,
each trail with its difficulty symbol. A lift's or trail's status is a picture: a cross for closed, and any other
picture for open (the page's key has only the two). A trail has a second place beside it that holds a picture when
it was groomed and nothing when it was not. A page whose lift or trail tables are not found, a lift or trail with
no picture at all, or a table row that does not read, fails instead of showing wrong numbers. The page's top gives
the new snow and the snowfall to date as a range (3" - 5"), the surface, and when the report was posted, in
Eastern time; it gives no base depth, so there is none, not a zero. The two ends of a range are carried as the
least and the most, and the single figure only where the two agree. The page does not say how long the new snow
fell over; it is carried as the last 24 hours. Standard library only.
"""
import html
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

URL = "https://www.madriverglen.com/conditions/"
# The page's difficulty pictures, in the words the page's difficulty symbols are keyed on.
LEVELS = {"greencircle": "Green", "bluesquare": "Blue", "blackdiamond": "Black", "doubleblackdiamond": "Double black"}
SECTION = re.compile(r'<div class="snowreport_sponsorarea fix">')
LIFT_ROW = re.compile(r"<tr>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*</tr>", re.S)
GROUP = re.compile(r'<th style="border-top:none;">([^<]+)</th>.*?</thead>(.*?)(?=<thead>|</table>)', re.S)
TRAIL_ROW = re.compile(r"<tr>\s*<td>(.*?)</td>\s*<td>\s*<p[^>]*>(.*?)</p>\s*<p[^>]*>(.*?)</p>\s*</td>\s*</tr>", re.S)
PICTURE = re.compile(r'<img[^>]*\ssrc="[^"]*/([^"/.]+)\.[a-z]+"', re.I)
UPDATED = re.compile(r"<p>\s*Updated:\s*([A-Z][a-z]+ [A-Z][a-z]+ \d{1,2}, \d{4} \d{1,2}:\d{2} [AP]M)\s*</p>")
FIGURE = re.compile(r"<td>\s*(New Snow|Snowfall to Date|Primary|Secondary):\s*<span>(.*?)</span>", re.S)
SPAN = re.compile(r'(\d+(?:\.\d+)?)\s*"?(?:\s*-\s*(\d+(?:\.\d+)?)\s*"?)?')
EASTERN = ZoneInfo("America/New_York")


def text_of(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def status_row(name: str, cell: str, difficulty: str | None) -> dict:
    """One lift or trail by the picture in its status cell: a cross is closed, any other picture is open."""
    pictures = PICTURE.findall(cell)
    if len(pictures) != 1:
        raise ValueError(f"{name} has {len(pictures)} status pictures, not one")
    status = "Closed" if "cross" in pictures[0].lower() else "Open"
    return {"Name": name, "Status": status, "StatusEnglish": status.lower(), "Difficulty": difficulty}


def trail_row(name_cell: str, cell: str, groomed: str) -> dict:
    symbols = PICTURE.findall(name_cell)
    row = status_row(text_of(name_cell), cell, LEVELS.get(symbols[0].lower(), "") if symbols else "")
    row["Grooming"] = "Yes" if PICTURE.search(groomed) else "No"
    return row


def number(said: str) -> float | int:
    value = float(said)
    return int(value) if value.is_integer() else value


def figures(name: str, said: str | None) -> dict:
    """A figure the page gives as 3" or as a range 3" - 5", under the Ikon feed's name: the two ends as the least
    and the most, and the single figure only where they agree. Empty where the page gives nothing."""
    said = (said or "").strip()
    if not said:
        return {f"{name}In": None}
    figure = SPAN.fullmatch(said)
    if not figure:
        raise ValueError(f"a snow figure does not read as a number or a range: {said}")
    low, high = number(figure.group(1)), number(figure.group(2) or figure.group(1))
    return {f"{name}In": low if low == high else None, f"{name}MinIn": low, f"{name}MaxIn": high}


def snow_report(page: str) -> dict:
    """The page's snowfall and surface in the shape of the Ikon feed's SnowReport, for the whole mountain."""
    stamp = UPDATED.search(page)
    if not stamp:
        raise ValueError("the report has no date")
    posted = datetime.strptime(stamp.group(1), "%A %B %d, %Y %I:%M %p").replace(tzinfo=EASTERN)
    said = {label: text_of(value) for label, value in FIGURE.findall(page)}
    if "New Snow" not in said:
        raise ValueError("the report has no new snow figure")
    surface = ", ".join(dict.fromkeys(word for word in (said.get("Primary"), said.get("Secondary")) if word))
    season = figures("SeasonTotal", said.get("Snowfall to Date"))
    return {"LastUpdate": posted.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "Resortwide": True,
            "BaseConditions": surface or None, **season,
            "BaseArea": {"Name": "Mountain", **figures("Last24Hours", said.get("New Snow"))}}


def parse(page: str, now: datetime) -> dict:
    sections = SECTION.split(page)[1:]
    lift_table = next((part for part in sections if "<h4>LIFTS</h4>" in part), None)
    trail_tables = next((part for part in sections if "<h4>TRAILS</h4>" in part), None)
    if lift_table is None or trail_tables is None:
        raise ValueError("the page's lift or trail tables were not found")
    body = lift_table.partition("<tbody>")[2].partition("</tbody>")[0]
    lifts = [status_row(text_of(name), cell, None) for name, cell in LIFT_ROW.findall(body)]
    if not lifts or len(lifts) != body.count("<tr>"):
        raise ValueError(f"the page lists {body.count('<tr>')} lifts but {len(lifts)} were read")
    areas = [{"Name": text_of(name), "Lifts": [], "Trails": [trail_row(*cells) for cells in TRAIL_ROW.findall(rows)]}
             for name, rows in GROUP.findall(trail_tables)]
    areas = [area for area in areas if area["Trails"]]
    # Every trail row of the page is one read, so a change in its shape fails instead of dropping runs.
    listed = sum(rows.count("<tr>") for _, rows in GROUP.findall(trail_tables))
    found = sum(len(area["Trails"]) for area in areas)
    if not found or found != listed:
        raise ValueError(f"the page lists {listed} trails but {found} were read")
    feed = {"Name": "Mad River Glen", "LastUpdate": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "MountainAreas": [{"Name": "Mad River Glen", "Lifts": lifts, "Trails": []}, *areas]}
    try:
        feed["SnowReport"] = snow_report(page)
    except ValueError as error:
        # A snow report that cannot be read costs only the snow report, not the lifts.
        print(f"Mad River Glen: snow report: {error}")
    return feed
