from datetime import datetime, timezone
from pathlib import Path

import pytest

from tahoe_snow.sources import powderking

# The page with its scripts, styles and comments taken out; the reader gives the same on the whole page.
PAGE = (Path(__file__).parent / "fixtures" / "powderking.html").read_text(encoding="utf-8")
NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)
CLOSED = '<font color="#a5d600"><span class="red">CLOSED</span> </font>'


def page(old: str, new: str, count: int = -1) -> str:
    assert old in PAGE
    return PAGE.replace(old, new, count)


def test_the_mountain_before_it_opens_reads_its_lifts_and_runs():
    # Powder King's page on 2026-11-26, a week before its delayed opening: three lifts and 38 numbered runs, all
    # closed.
    feed = powderking.parse(PAGE, NOW)
    assert feed["Name"] == "Powder King" and feed["LastUpdate"] == "2026-11-26T18:00:00Z"
    assert [area["Name"] for area in feed["MountainAreas"]] == ["Powder King"]
    area = feed["MountainAreas"][0]
    # The page writes "CHAIR LIFT", "T - BAR" and "HANDLE TOW (Strawberry Fields)".
    assert area["Lifts"] == [
        {"Name": "Chair Lift", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None},
        {"Name": "T-Bar", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None},
        {"Name": "Handle Tow (Strawberry Fields)", "Status": "Closed", "StatusEnglish": "closed", "Difficulty": None}]
    runs = {run["Name"]: run for run in area["Trails"]}
    # Runs 17 and 18 give an upper and a lower half each, and run 16 is written as two rows: 41 in all.
    assert len(area["Trails"]) == 41 == len(runs)
    assert {run["StatusEnglish"] for run in runs.values()} == {"closed"}
    assert area["Trails"][0] == {"Name": "Old Bullwheel Run", "Status": "Closed", "StatusEnglish": "closed",
                                 "Difficulty": "Black"}
    assert area["Trails"][-1]["Name"] == "Strawberry Fields" and "#9" in runs and "Ferrie's Folly" in runs
    assert [name for name in runs if "(" in name] == [
        "Roll Over Beethoven (Upper)", "Roll Over Beethoven (Lower)", "No Where Man (Upper)", "No Where Man (Lower)",
        "Hard Days Night (Upper)", "Hard Days Night (Lower)"]
    # The dot's colour is the difficulty: an uncoloured dot is the page's "Most Difficult/Advanced".
    assert (runs["Chester's Bypass"]["Difficulty"], runs["Chester's"]["Difficulty"],
            runs["Chester's Challenge"]["Difficulty"]) == ("Green", "Blue", "Black")
    assert (runs["Roll Over Beethoven (Upper)"]["Difficulty"], runs["Roll Over Beethoven (Lower)"]["Difficulty"]) == (
        "Blue", "Green")
    levels = [run["Difficulty"] for run in runs.values()]
    assert [levels.count(level) for level in ("Green", "Blue", "Black")] == [15, 16, 10]


def test_the_snow_table_gives_each_place_s_depth_in_inches_and_when_it_was_updated():
    snow = powderking.parse(PAGE, NOW)["SnowReport"]
    # "LAST UPDATED: 11am Thursday November 12 2026", in the zone the machine's time zone data gives Vancouver
    # (seven hours behind UTC all year since British Columbia stopped changing its clocks); nothing on the ground yet.
    assert snow["LastUpdate"] == "2026-11-12T18:00:00Z" and snow["Resortwide"] is False
    assert snow["BaseArea"] == {"Name": "Day Lodge", "Last24HoursIn": 0, "Last48HoursIn": 0, "Last72HoursIn": 0,
                                "BaseIn": 0}
    assert snow["MidMountainArea"]["Name"] == "Top Chair" and snow["SummitArea"]["Name"] == "Top T-Bar"
    assert snow["BaseConditions"] is None and snow["SeasonTotalIn"] is None


def test_centimetres_are_given_in_inches():
    row = ('<td style="width: 140px;"><strong>Top T-Bar</strong></td>\n\t\t\t'
           '<td style="width: 49px; text-align: center;">')
    changed = page(row + "0</td>\n\t\t\t<td style=\"width: 50px; text-align: center;\">0</td>\n\t\t\t"
                   "<td style=\"width: 66px; text-align: center;\">0</td>\n\t\t\t"
                   "<td style=\"width: 67px; text-align: center;\">0</td>",
                   row + "12</td>\n\t\t\t<td style=\"width: 50px; text-align: center;\">20cm</td>\n\t\t\t"
                   "<td style=\"width: 66px; text-align: center;\"></td>\n\t\t\t"
                   "<td style=\"width: 67px; text-align: center;\">254</td>")
    snow = powderking.parse(changed, NOW)["SnowReport"]
    # An empty figure is left out.
    assert snow["SummitArea"] == {"Name": "Top T-Bar", "Last24HoursIn": 4.7, "Last48HoursIn": 7.9, "BaseIn": 100}
    assert snow["BaseArea"]["BaseIn"] == 0


def test_open_lifts_and_runs_read_as_open():
    changed = page("CHAIR LIFT&nbsp;<span class=\"red\">- Closed</span>",
                   "CHAIR LIFT&nbsp;<span class=\"green\">- Open</span>")
    changed = changed.replace("<strong>- Closed</strong>", "<strong>- ON HOLD</strong>")
    changed = changed.replace(CLOSED, '<font color="#a5d600"><span class="green">OPEN</span> </font>', 20)
    area = powderking.parse(changed, NOW)["MountainAreas"][0]
    assert [(lift["Name"], lift["Status"], lift["StatusEnglish"]) for lift in area["Lifts"]] == [
        ("Chair Lift", "Open", "open"), ("T-Bar", "On hold", "on hold"),
        ("Handle Tow (Strawberry Fields)", "Closed", "closed")]
    runs = {run["Name"]: run["StatusEnglish"] for run in area["Trails"]}
    # The twentieth status on the page is the upper half of Hard Days Night.
    assert sum(status == "open" for status in runs.values()) == 20
    assert (runs["Hard Days Night (Upper)"], runs["Hard Days Night (Lower)"]) == ("open", "closed")


def test_a_page_that_has_changed_is_refused():
    with pytest.raises(ValueError, match="lift report was not found"):
        powderking.parse(page("LIFT REPORT:", "LIFTS:"), NOW)
    with pytest.raises(ValueError, match="not a name, a dash and a status"):
        powderking.parse(page("CHAIR LIFT&nbsp;<span class=\"red\">- Closed</span>", "CHAIR LIFT"), NOW)
    with pytest.raises(ValueError, match="run report was not found"):
        powderking.parse(page("OPEN RUN REPORT:", "RUNS:"), NOW)
    with pytest.raises(ValueError, match="not a number and a name"):
        powderking.parse(page("<strong>3 Satisfaction</strong>", "<strong>Satisfaction</strong>"), NOW)
    with pytest.raises(ValueError, match="a dot coloured \\['orange'\\]"):
        powderking.parse(page('<span class="blue2">⬤</span></td>\n\t\t\t<td style="width: 226px;"><strong>5 Che',
                              '<span class="orange">⬤</span></td>\n\t\t\t<td style="width: 226px;"><strong>5 Che'),
                         NOW)
    with pytest.raises(ValueError, match="where its difficulty's dot should be"):
        powderking.parse(page('<td style="width: 37px;">⬤</td>', '<td style="width: 37px;"></td>', 1), NOW)
    with pytest.raises(ValueError, match="Satisfaction has the status '50%', not a word"):
        powderking.parse(page("3 Satisfaction</strong></td>\n\t\t\t<td style=\"width: 277px;\">" + CLOSED,
                              "3 Satisfaction</strong></td>\n\t\t\t<td style=\"width: 277px;\">50%"), NOW)
    with pytest.raises(ValueError, match="names a run twice"):
        powderking.parse(page("<strong>3 Satisfaction</strong>", "<b>3 Infusion</b>"), NOW)
    with pytest.raises(ValueError, match="no lifts or no runs"):
        powderking.parse(page("<table", "<div"), NOW)


def test_a_snow_report_that_cannot_be_read_costs_only_the_snow_report():
    for old, new in (("LAST UPDATED:", "UPDATED:"), ("November&nbsp; 12", "Smarch&nbsp; 12"),
                     ("<strong>Base cm</strong>", "<strong>Base in</strong>"),
                     ("<strong>Top Chair</strong>", "<strong>Summit</strong>"), ("SNOW BASE", "SNOW")):
        feed = powderking.parse(page(old, new), NOW)
        assert "SnowReport" not in feed and len(feed["MountainAreas"][0]["Lifts"]) == 3
