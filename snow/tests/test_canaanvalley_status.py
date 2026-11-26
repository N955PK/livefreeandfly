from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import canaanvalley

# The page's own part, with its scripts, styles, drawings and hours taken out; the reader gives the same on the
# whole page.
PAGE = (Path(__file__).parent / "fixtures" / "canaanvalley.html").read_text()
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)
CLOSED = "<span class=\"status\">Closed</span>"
DASH = "<span>&ndash;</span>\n          {label}</li>"


def page(old: str, new: str, count: int = -1) -> str:
    assert old in PAGE
    return PAGE.replace(old, new, count)


def figure(text: str, label: str, said: str) -> str:
    assert DASH.format(label=label) in text
    return text.replace(DASH.format(label=label), DASH.format(label=label).replace("&ndash;", said))


def test_the_closed_ski_area_reads_its_lifts_and_no_trails():
    # Canaan Valley's page on 2026-11-26, last updated in February: six lifts closed and empty tables of trails.
    feed = canaanvalley.parse(PAGE, NOW)
    assert feed["Name"] == "Canaan Valley" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    # The out-of-season conditions are dashes.
    assert "SnowReport" not in feed
    assert len(feed["MountainAreas"]) == 1 and feed["MountainAreas"][0]["Trails"] == []
    # The tube park's two lifts are counted against the page's "0/6" and left out.
    assert feed["MountainAreas"][0]["Lifts"] == [
        {"Name": "\"A\" Lift", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None},
        {"Name": "\"B\" Lift", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None},
        {"Name": "\"C\" Lift", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None},
        {"Name": "Magic Carpet", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}]


def test_the_snow_report_is_read_once_the_page_gives_its_figures():
    filled = figure(figure(figure(PAGE, "Base Depth", "24&quot;"), "Snowfall<br>(Season Total)", "61.5&quot;"),
                    "Primary Surface", "Packed Powder")
    filled = filled.replace("<span>&ndash;</span>\n          Snowfall<br>(Last 24 hrs)", "<span>3&quot;</span>\n"
                            "          Snowfall<br>(Last 24 hrs)")
    snow = canaanvalley.parse(filled, NOW)["SnowReport"]
    # "Last Updated: February 10, 2026, 2:30pm" in Eastern time, five hours behind UTC in February.
    assert snow["LastUpdate"] == "2026-02-10T19:30:00Z" and snow["Resortwide"] is True
    assert snow["BaseArea"] == {"Name": "Mountain", "BaseIn": 24, "Last24HoursIn": 3}
    assert (snow["SeasonTotalIn"], snow["StormTotalIn"], snow["BaseConditions"]) == (61.5, None, "Packed Powder")
    ranged = canaanvalley.parse(figure(PAGE, "Base Depth", "18-36&quot;"), NOW)["SnowReport"]["BaseArea"]
    assert (ranged["BaseMinIn"], ranged["BaseMaxIn"]) == (18, 36) and "BaseIn" not in ranged


def test_an_open_lift_is_read_while_the_page_is_fresh():
    opened = page(CLOSED, "<span class=\"status\">Open</span>", 2).replace("0/6</h3>", "2/6</h3>")
    lifts = canaanvalley.parse(opened, datetime(2026, 2, 11, 14, 0, tzinfo=timezone.utc))["MountainAreas"][0]["Lifts"]
    assert [(lift["Status"], lift["StatusEnglish"]) for lift in lifts] == [("Open", "open")] * 2 + [
        ("Closed", "closed")] * 2
    # Left up into the autumn, the same page is last season's.
    with pytest.raises(ValueError, match="last updated 2026-02-10 and has lifts open: it is last season's"):
        canaanvalley.parse(opened, NOW)


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="counts 0 of 6 lifts open but 1 of 6 were read"):
        canaanvalley.parse(page(CLOSED, "<span class=\"status\">Open</span>", 1), NOW)
    with pytest.raises(ValueError, match="counts 0 of 7 lifts open but 0 of 6 were read"):
        canaanvalley.parse(page("0/6</h3>", "0/7</h3>"), NOW)
    with pytest.raises(ValueError, match="counts 0 of 6 lifts open but 0 of 5 were read"):
        canaanvalley.parse(page("<span class=\"name\">Magic Carpet</span>", "<b>Magic Carpet</b>"), NOW)
    with pytest.raises(ValueError, match="has the status '', not a word"):
        canaanvalley.parse(page(CLOSED, "<span class=\"status\"></span>", 1), NOW)
    with pytest.raises(ValueError, match="does not say when it was last updated"):
        canaanvalley.parse(page("February 10, 2026, 2:30pm", "this afternoon"), NOW)
    with pytest.raises(ValueError, match="the page's lifts were not found"):
        canaanvalley.parse("<html><body>Page not found</body></html>", NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    feed = canaanvalley.parse(figure(PAGE, "Base Depth", "deep"), NOW)
    assert "SnowReport" not in feed and len(feed["MountainAreas"][0]["Lifts"]) == 4
