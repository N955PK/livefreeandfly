"""The runner for the mountains that each have a reader of their own."""
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from tahoe_snow import config
from tahoe_snow.sources import independents

NOW = datetime(2026, 11, 24, 17, 0, tzinfo=timezone.utc)


def feed(open_lifts: int, snow: dict | None) -> dict:
    lifts = [{"Name": f"Chair {n}", "Status": "Open" if n < open_lifts else "Closed",
              "StatusEnglish": "open" if n < open_lifts else "closed", "Difficulty": None} for n in range(3)]
    out = {"Name": "Somewhere", "LastUpdate": "2026-11-24T17:00:00Z",
           "MountainAreas": [{"Name": "Somewhere", "Lifts": lifts, "Trails": []}]}
    if snow is not None:
        out["SnowReport"] = snow
    return out


def test_every_reader_is_a_mountain_of_new_england_the_tetons_the_wasatch_or_colorado_and_says_where_its_page_is():
    for key, module in independents.MODULES.items():
        assert config.ALL_RESORTS[key].region in ("newengland", "tetons", "wasatch", "colorado", "shasta", "okanagan", "bccoast", "quebec", "rockies", "powderhighway", "eastkootenays",
                                                  "montana", "sunvalley", "oregon", "newmexico", "alaska", "swcolorado",
                                                  "michigan", "southutah", "arizona", "lasvegas",
                                                  "nwmontana", "westidaho", "lakesuperior", "socal", "inlandnw", "midatlantic", "newyork", "juneau", "blackhills", "northbc", "ontario",
                                                  "mammoth", "wyoming", "newfoundland"), key
        assert hasattr(module, "URL") or hasattr(module, "URLS"), key
        assert callable(module.parse), key
    assert len(independents.MODULES) == 130
    assert [key for key in independents.MODULES if config.ALL_RESORTS[key].region == "swcolorado"] == [
        "telluride", "monarch", "purgatory", "sunlight", "powderhorn"]
    # Aspen Snowmass's site gives its four mountains in one read.
    assert list(independents.GROUPS) == ["aspensnowmass"]
    assert [key for key in independents.MODULES if config.ALL_RESORTS[key].region in (
        "montana", "sunvalley", "oregon", "newmexico", "alaska")] == [
        "bigsky", "sunvalley", "dollar", "hoodmeadows", "cooperspur", "willamettepass", "taos", "redriver", "sipapu",
        "skisantafe", "pajarito", "alyeska", "arcticvalley", "timberline", "skibowl", "hoodoo", "bachelor",
        "showdown"]
    assert [key for key in independents.MODULES if config.ALL_RESORTS[key].region == "okanagan"] == [
        "bigwhite", "silverstar", "sunpeaks"]
    assert [key for key in independents.MODULES if config.ALL_RESORTS[key].region == "shasta"] == ["shastaskipark", "ashland"]
    assert [key for key in independents.MODULES if config.ALL_RESORTS[key].region == "colorado"] == ["copper", "loveland", "eldora"]
    assert [key for key in independents.MODULES if config.ALL_RESORTS[key].region == "wasatch"] == [
        "alta", "snowbird", "brighton", "snowbasin", "powdermountain", "sundance"]
    assert [key for key in independents.MODULES if config.ALL_RESORTS[key].region == "tetons"] == ["jacksonhole", "targhee"]


def test_a_range_is_given_its_middle_and_a_single_figure_is_left_alone():
    snow = {"LastUpdate": "2026-11-24T12:00:00Z", "Resortwide": True,
            "BaseArea": {"BaseIn": None, "BaseMinIn": 26, "BaseMaxIn": 40, "Last24HoursIn": 3,
                         "Last24HoursMinIn": 2, "Last24HoursMaxIn": 6}}
    area = independents.settled(feed(2, snow), NOW)["SnowReport"]["BaseArea"]
    assert (area["BaseIn"], area["BaseMinIn"], area["BaseMaxIn"]) == (33.0, 26, 40)
    assert area["Last24HoursIn"] == 3
    empty = {"LastUpdate": "2026-11-24T12:00:00Z", "BaseArea": {"BaseIn": None, "BaseMinIn": None, "BaseMaxIn": None}}
    assert independents.settled(feed(2, empty), NOW)["SnowReport"]["BaseArea"]["BaseIn"] is None


def test_a_closed_mountains_undated_or_old_report_is_left_out():
    base = {"BaseArea": {"BaseIn": 25}}
    assert "SnowReport" not in independents.settled(feed(0, {**base, "LastUpdate": None}), NOW)
    assert "SnowReport" not in independents.settled(feed(0, {**base, "LastUpdate": "2026-04-08T12:00:00Z"}), NOW)
    assert "SnowReport" not in independents.settled(feed(0, {**base, "LastUpdate": "last spring"}), NOW)
    # Dated within two weeks, or with a lift turning, it stays.
    assert "SnowReport" in independents.settled(feed(0, {**base, "LastUpdate": "2026-11-16T13:36:00Z"}), NOW)
    assert "SnowReport" in independents.settled(feed(1, {**base, "LastUpdate": None}), NOW)
    assert "SnowReport" not in independents.settled(feed(0, None), NOW)


def test_a_mountain_with_no_lifts_posted_is_left_out():
    empty = {"Name": "Somewhere", "LastUpdate": "2026-11-24T17:00:00Z", "MountainAreas": [{"Name": "Somewhere", "Lifts": [], "Trails": []}]}
    assert not independents.posted(empty)
    assert independents.posted(feed(0, None))


STAMP = "%Y-%m-%dT%H:%M:%SZ"


class Clock(datetime):
    """The runner's clock, held where a test puts it."""
    at = NOW

    @classmethod
    def now(cls, tz=None):
        return cls.at


def site(result) -> SimpleNamespace:
    """A reader whose page gives ``result``, or cannot be read when that is an error."""
    def parse(page, now):
        if isinstance(result, Exception):
            raise result
        return result
    return SimpleNamespace(URL="https://example.invalid/", parse=parse)


def named(name: str, open_lifts: int = 1) -> dict:
    return {**feed(open_lifts, None), "Name": name}


@pytest.fixture
def runner(tmp_path, monkeypatch):
    """Run the readers given over pages that are never fetched, and give back the file written (None if none was)."""
    monkeypatch.setattr(independents, "datetime", Clock)
    monkeypatch.setattr(independents, "fetch", lambda url, method="GET": "")
    out = tmp_path / "independents.json"

    def run(modules: dict, groups: dict | None = None, last: dict | None = None, now: datetime = NOW):
        monkeypatch.setattr(Clock, "at", now)
        monkeypatch.setattr(independents, "MODULES", modules)
        monkeypatch.setattr(independents, "GROUPS", groups or {})
        if last is not None:
            out.write_text(json.dumps(last))
        code = independents.main(str(out))
        return code, json.loads(out.read_text()) if out.exists() else None
    return run


def ago(minutes: int) -> str:
    return (NOW - timedelta(minutes=minutes)).strftime(STAMP)


def test_every_reading_says_when_it_was_read(runner):
    code, written = runner({"jaypeak": site(named("Jay Peak")), "burke": site(named("Burke"))})
    assert code == 0 and written["updated"] == "2026-11-24T17:00:00Z"
    assert [entry["ReadAt"] for entry in written["resorts"].values()] == ["2026-11-24T17:00:00Z"] * 2


def test_a_mountain_whose_read_fails_keeps_its_last_reading_while_that_is_under_ninety_minutes_old(runner, capsys):
    last = {"updated": ago(5), "resorts": {
        "jaypeak": {**named("Jay Peak", 3), "ReadAt": ago(89)}, "burke": {**named("Burke", 3), "ReadAt": ago(90)},
        "cannon": {**named("Cannon", 3), "ReadAt": ago(5)}}}
    code, written = runner({"jaypeak": site(OSError("timed out")), "burke": site(ValueError("no lift table")),
                            "cannon": site(named("Cannon", 1)), "magic": site(KeyError("lifts"))}, last=last)
    assert code == 0 and list(written["resorts"]) == ["jaypeak", "cannon"]
    # The kept reading is the earlier one, whole, and still says when it was read; the fresh one replaces its own.
    assert written["resorts"]["jaypeak"] == last["resorts"]["jaypeak"]
    assert written["resorts"]["cannon"]["ReadAt"] == "2026-11-24T17:00:00Z"
    lifts = written["resorts"]["cannon"]["MountainAreas"][0]["Lifts"]
    assert sum(lift["StatusEnglish"] == "open" for lift in lifts) == 1
    out = capsys.readouterr().out
    assert f"jaypeak: timed out; showing its reading of {ago(89)}" in out
    assert "burke: no lift table\n" in out and "magic: 'lifts'\n" in out


def test_a_reading_kept_through_one_failure_is_not_made_newer_by_being_kept(runner):
    modules = {"jaypeak": site(OSError("timed out")), "burke": site(named("Burke"))}
    last = {"updated": ago(5), "resorts": {"jaypeak": {**named("Jay Peak"), "ReadAt": ago(80)}}}
    _, written = runner(modules, last=last)
    assert written["resorts"]["jaypeak"]["ReadAt"] == ago(80)
    # Ten minutes on, the file just written is the one before, and the reading in it is ninety minutes old.
    _, written = runner(modules, now=NOW + timedelta(minutes=10))
    assert list(written["resorts"]) == ["burke"]


def test_a_file_written_before_readings_were_stamped_is_judged_by_its_own_time(runner):
    modules = {"jaypeak": site(OSError("timed out")), "burke": site(named("Burke"))}
    _, written = runner(modules, last={"updated": ago(20), "resorts": {"jaypeak": named("Jay Peak")}})
    assert written["resorts"]["jaypeak"]["ReadAt"] == ago(20)
    _, written = runner(modules, last={"updated": ago(120), "resorts": {"jaypeak": named("Jay Peak")}})
    assert list(written["resorts"]) == ["burke"]
    # A file that cannot be read, or says nothing of when, keeps nothing and does not stop the pass.
    jay = {"jaypeak": named("Jay Peak")}
    for last in ({"resorts": jay}, {"updated": "lately", "resorts": jay}, {"updated": ago(5), "resorts": ["jaypeak"]},
                 ["jaypeak"]):
        code, written = runner(modules, last=last)
        assert code == 0 and list(written["resorts"]) == ["burke"], last


def test_a_mountain_that_was_read_but_has_posted_no_lifts_is_left_out_though_it_was_there_before(runner, capsys):
    empty = {"Name": "Ski Park", "LastUpdate": None, "MountainAreas": [{"Name": "Ski Park", "Lifts": [], "Trails": []}]}
    last = {"updated": ago(5), "resorts": {"shastaskipark": {**named("Ski Park"), "ReadAt": ago(5)}}}
    code, written = runner({"shastaskipark": site(empty), "burke": site(named("Burke"))}, last=last)
    assert code == 0 and list(written["resorts"]) == ["burke"]
    assert "shastaskipark: no lifts posted yet" in capsys.readouterr().out


def test_with_every_read_failing_the_kept_readings_are_still_written_and_with_none_kept_nothing_is(runner):
    modules = {"jaypeak": site(OSError("timed out")), "burke": site(OSError("timed out"))}
    recent = {"updated": ago(5), "resorts": {"burke": {**named("Burke"), "ReadAt": ago(5)}}}
    code, written = runner(modules, last=recent)
    assert code == 0 and list(written["resorts"]) == ["burke"] and written["updated"] == "2026-11-24T17:00:00Z"
    stale = {"updated": ago(300), "resorts": {"burke": {**named("Burke"), "ReadAt": ago(300)}}}
    # Nothing to write: the file is left as it was, so its own time shows how long the reads have failed.
    assert runner(modules, last=stale) == (1, stale)


def test_a_site_of_several_mountains_keeps_each_ones_last_reading(runner):
    def group(result):
        return SimpleNamespace(**vars(site(result)), MOUNTAINS={"aspen": (), "highlands": (), "snowmass": ()})

    last = {"updated": ago(5), "resorts": {key: {**named(key), "ReadAt": ago(10)} for key in ("aspen", "highlands")}}
    modules = {"burke": site(named("Burke"))}
    # The whole site fails: the mountains it had are kept, and the one it never had is not made up.
    _, written = runner(modules, {"aspensnowmass": group(OSError("timed out"))}, last=last)
    assert [(key, entry["ReadAt"]) for key, entry in written["resorts"].items()] == [
        ("burke", ago(0)), ("aspen", ago(10)), ("highlands", ago(10))]
    # The site answers but leaves one mountain out, which is that mountain's failure alone.
    answered = {"aspen": named("Aspen Mountain"), "snowmass": named("Snowmass")}
    _, written = runner(modules, {"aspensnowmass": group(answered)}, last=last)
    assert [(key, entry["ReadAt"]) for key, entry in written["resorts"].items()] == [
        ("burke", ago(0)), ("aspen", ago(0)), ("highlands", ago(10)), ("snowmass", ago(0))]


def test_every_site_of_several_mountains_names_them():
    for name, module in independents.GROUPS.items():
        assert set(module.MOUNTAINS) <= set(config.ALL_RESORTS), name


def test_the_sites_are_read_several_at_once_and_written_in_the_readers_order(runner, monkeypatch):
    import threading
    together = threading.Barrier(4, timeout=10)

    def slow(name):
        def parse(page, now):
            # Each read waits for three others to be under way, which cannot happen one read at a time.
            together.wait()
            return named(name)
        return SimpleNamespace(URL="https://example.invalid/", parse=parse)

    monkeypatch.setattr(independents, "WORKERS", 4)
    keys = [f"mountain{n}" for n in range(8)]
    code, written = runner({key: slow(key) for key in keys}, {"pair": SimpleNamespace(
        URL="https://example.invalid/", MOUNTAINS={"aspen": (), "snowmass": ()},
        parse=lambda page, now: {"aspen": named("Aspen Mountain"), "snowmass": named("Snowmass")})})
    assert code == 0 and list(written["resorts"]) == keys + ["aspen", "snowmass"]


def test_the_real_readers_are_run_in_their_own_order_without_the_network(runner, monkeypatch):
    read = []
    groups = list(independents.GROUPS.values())
    monkeypatch.setattr(independents, "read", lambda module, now: read.append(module) or (
        {key: named(key) for key in module.MOUNTAINS} if module in groups else named("Somewhere")))
    code, written = runner(dict(independents.MODULES), dict(independents.GROUPS))
    assert code == 0 and len(read) == len(independents.MODULES) + len(independents.GROUPS)
    assert list(written["resorts"]) == list(independents.MODULES) + [
        key for module in independents.GROUPS.values() for key in module.MOUNTAINS]
