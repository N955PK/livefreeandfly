"""Black Mountain's lifts and trails, and its snow report, from its conditions page (blackmt.com/conditions).

Black Mountain of Jackson, New Hampshire. The page is built on the server, so the browser cannot read it from
another site; a scheduled job reads it and writes one small file the page reads, in the shape of the Ikon feed the
rest of the page uses. The page is kept by hand in a site builder: under "Trail & Lift Status" each name and each
status is a text box of its own, a run of names followed by as many statuses in the same order, under a heading for
the lifts and one for each kind of trail (Beginner, Intermediate, Advanced, Experts Only, Extreme / Hike To
Terrain). A status is one of the words the resort uses (Open, Closed, As Needed and the like); a run whose names
and statuses do not pair off, which is also what an unknown status word makes, fails instead of showing wrong
numbers.

The snow report is the box of figures above the status, in the shape of the Ikon feed's snow report: the 24-hour
and season snowfall, the surface, the counts of open and groomed trails, and the resort's own words. The page gives
no base depth, so there is none, not a zero. It dates its report by the day only, and not always, so it is stamped
at noon Eastern, or left undated. A figure that does not read as a number stays empty. Standard library only.
"""
import html
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

URL = "https://www.blackmt.com/conditions"
EASTERN = ZoneInfo("America/New_York")
MAIN = re.compile(r"<main\b.*?</main>", re.S)
BOX = "data-testid=\"richTextElement\""
LINE = re.compile(r"<(h\d|p)\b[^>]*>(.*?)</\1>", re.S)
STATUS_HEADING = "trail & lift status"
LIFT_HEADING = "lifts"
# The page's trail headings, in the words the page's difficulty symbols are keyed on.
LEVELS = {"beginner": "Green", "intermediate": "Blue", "advanced": "Black", "experts only": "Double black",
          "extreme / hike to terrain": "Double black"}
STATUSES = {"open", "closed", "as needed", "on hold", "hold", "delayed", "expected"}
FACT = re.compile(r"(Updated|Trails Open|Percent Open|Trails Groomed|Lifts Open|24-hour Snow Total|Season Snow Total|"
                  r"Snow Conditions|Today's High)\s*:\s*(.*)", re.I)
MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december")
DAY = re.compile(r"\b(" + "|".join(MONTHS) + r")\s+(\d{1,2})(?:st|nd|rd|th)?\b,?(?:\s+(\d{4}))?", re.I)
DATED = re.compile(r"(updated|snow report)\b", re.I)


def text_of(fragment: str) -> str:
    plain = html.unescape(re.sub(r"<[^>]+>", "", fragment)).replace("​", "")
    return re.sub(r"\s+", " ", plain).strip()


def status_row(name: str, status: str, difficulty: str | None) -> dict:
    words = status.capitalize()
    return {"Name": name, "Status": words, "StatusEnglish": words.lower(), "Difficulty": difficulty}


def boxes(page: str) -> list:
    """The page's text boxes in order, each the list of its lines as (heading or not, text)."""
    main = MAIN.search(page)
    if not main:
        raise ValueError("the page's main part was not found")
    found = [[(tag != "p", text_of(body)) for tag, body in LINE.findall(box)] for box in main.group(0).split(BOX)[1:]]
    return [[line for line in box if line[1]] for box in found]


def inches(said: str) -> float | int | None:
    figure = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(?:\"|”|in\.?|inches)?", said.strip())
    if not figure:
        return None
    value = float(figure.group(1))
    return int(value) if value.is_integer() else value


def count(said: str) -> int | None:
    return int(said) if re.fullmatch(r"\d+", said.strip()) else None


def posted(lines: list, now: datetime) -> str | None:
    """The day the report says it is of ("Updated: November 20th 2026", "Snow Report – Sunday, March 1"), at noon
    Eastern; a day given without its year is the latest such day not after today. None where it gives no day."""
    for line in lines:
        day = DAY.search(line) if DATED.match(line) else None
        if not day:
            continue
        month, date = MONTHS.index(day.group(1).lower()) + 1, int(day.group(2))
        today = now.astimezone(EASTERN)
        year = int(day.group(3)) if day.group(3) else today.year
        when = datetime(year, month, date, 12, tzinfo=EASTERN)
        if not day.group(3) and when > today + timedelta(days=1):
            when = when.replace(year=year - 1)
        return when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return None


def snow_report(found: list, now: datetime) -> dict | None:
    """The box of figures in the shape of the Ikon feed's SnowReport: snowfall and surface for the whole mountain
    (the page gives no base depth). None when the page has no such box."""
    box = next((box for box in found if any(text.lower().startswith("lifts open") for _, text in box)), None)
    if box is None:
        return None
    lines = [text for _, text in box]
    facts = {fact.group(1).lower(): fact.group(2).strip() for fact in map(FACT.fullmatch, lines) if fact}
    words = [line for line in lines if not FACT.fullmatch(line)]
    return {"LastUpdate": posted(lines, now), "Resortwide": True, "BaseConditions": facts.get("snow conditions") or None,
            "SeasonTotalIn": inches(facts.get("season snow total", "")),
            "TotalOpenTrails": count(facts.get("trails open", "")), "GroomedTrails": count(facts.get("trails groomed", "")),
            "BaseArea": {"Name": "Mountain", "Last24HoursIn": inches(facts.get("24-hour snow total", ""))},
            "Report": "".join(f"<p>{html.escape(line)}</p>" for line in words) or None, "Alert": None}


def parse(page: str, now: datetime) -> dict:
    found = boxes(page)
    lines = [line for box in found for line in box]
    start = next((n for n, (heading, text) in enumerate(lines) if heading and text.lower() == STATUS_HEADING), None)
    if start is None:
        raise ValueError("the page's trail and lift status was not found")
    groups, names, states = [], [], []

    def pair_off():
        if len(names) != len(states):
            raise ValueError(f"{len(names)} names but {len(states)} statuses under {groups[-1][0] if groups else 'no heading'}"
                             f" (near {(names or states)[-1]})")
        groups[-1][1].extend(zip(names, states))
        names.clear()
        states.clear()

    for heading, text in lines[start + 1:]:
        if heading:
            if groups:
                pair_off()
            groups.append((text, []))
        elif not groups:
            raise ValueError(f"{text} is under no heading")
        elif text.lower() in STATUSES:
            if len(states) >= len(names):
                raise ValueError(f"a status with no name under {groups[-1][0]}")
            states.append(text)
        else:
            # A name after statuses starts the next run, which the last one must have paired off.
            if states:
                pair_off()
            names.append(text)
    if groups:
        pair_off()
    if not groups or groups[0][0].lower() != LIFT_HEADING or not groups[0][1]:
        raise ValueError("the page lists no lifts")
    lifts = [status_row(name, state, None) for name, state in groups[0][1]]
    areas = [{"Name": name.title() if name.isupper() else name, "Lifts": [],
              "Trails": [status_row(trail, state, LEVELS.get(name.lower(), "")) for trail, state in rows]}
             for name, rows in groups[1:] if rows]
    feed = {"Name": "Black Mountain", "LastUpdate": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "MountainAreas": [{"Name": "Black Mountain", "Lifts": lifts, "Trails": []}, *areas]}
    snow = snow_report(found, now)
    if snow:
        feed["SnowReport"] = snow
    return feed
