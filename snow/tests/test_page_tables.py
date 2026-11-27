"""The page keeps several tables by hand, keyed by mountain or region. Each must name only what the config has."""
import re

from tahoe_snow.config import ALL_REGIONS, ALL_RESORTS, ROOT

PAGE = (ROOT / "index.html").read_text()


def table(name: str) -> str:
    """The text of ``const <name> = {...};`` or ``[...]``, from its opening to the line that closes it."""
    start = PAGE.index(f"const {name} = ")
    return PAGE[start:PAGE.index(";\n", start)]


def keys(text: str) -> set:
    return set(re.findall(r"(?:[{,]\s*|^\s*)([a-z][a-z0-9]*): ", text, re.M))


def test_the_pages_regions_are_the_configs_and_each_stands_in_one_part_of_the_menu():
    block = PAGE[PAGE.index("const REGIONS = {"):PAGE.index("const REGION_PARTS")]
    regions = set(re.findall(r'\n  (\w+): \{name: "', block))
    assert regions == set(ALL_REGIONS)
    listed = re.findall(r'"([a-z]+)"', re.sub(r'\["(USA|Canada)", "[^"]+",', "", table("REGION_PARTS")))
    assert sorted(listed) == sorted(ALL_REGIONS)
    # Every mountain a region's map pills name is one of that region's.
    for key, body in re.findall(r'\n  (\w+): \{name: "(.*?)(?=\n  \w+: \{name: "|\Z)', block, re.S):
        for mountain in re.findall(r'"([a-z0-9]+)"', " ".join(re.findall(r"mountains: \[([^\]]*)\]", body))):
            assert ALL_RESORTS[mountain].region == key, (key, mountain)


def test_the_classics_and_the_place_names_are_keyed_by_mountains_and_regions_that_exist():
    classics = set(re.findall(r"(\w+): \[\[", table("CLASSICS")))
    assert classics <= set(ALL_RESORTS)
    numbers = sorted(int(n) for n in re.findall(r"\[(\d+), \"", table("CLASSICS")))
    assert numbers == list(range(1, 51))
    assert keys(table("CLASSIC_PEAK")) <= classics
    states = table("STATE_OF")
    named = [key for words in re.findall(r'": "([a-z0-9 ]+)"', states) for key in words.split()]
    assert named and set(named) <= set(ALL_RESORTS) and len(named) == len(set(named))
    assert keys(table("REGION_IN")) <= set(ALL_REGIONS)
    assert keys(table("PEAK_STATE")) <= set(ALL_REGIONS)
    # Between them the three tables give every mountain a state or province.
    placed = keys(table("REGION_IN")) | keys(table("PEAK_STATE"))
    assert all(resort.key in named or resort.region in placed for resort in ALL_RESORTS.values())


def test_the_short_names_and_the_summit_points_are_keyed_by_mountains_that_exist():
    assert keys(table("SHORT")) <= set(ALL_RESORTS)
    assert set(re.findall(r"(\w+): \[-?\d", table("PEAK_AT"))) <= set(ALL_RESORTS)


def test_every_logo_mark_listed_on_the_page_has_its_picture():
    # The page draws logos/<key>.png behind the name of each resort in LOGO_MARKS; a key with no picture would
    # draw nothing.
    import re
    from pathlib import Path

    from tahoe_snow.config import ALL_RESORTS

    root = Path(__file__).parent.parent
    listed = set(re.search(r'const LOGO_MARKS = new Set\("([^"]*)"\.split', (root / "index.html").read_text()).group(1).split())
    pictures = {path.stem for path in (root / "logos").glob("*.png")}
    # A picture may wait in the folder unlisted (made, but not judged good enough to show); none may be listed
    # without its picture.
    # A mountain with no logo of its own is drawn its resort's (LOGO_SHARED), which must have a picture.
    shared = dict(re.findall(r'(\w+): "(\w+)"', table("LOGO_SHARED")))
    assert set(shared) <= listed and set(shared.values()) <= pictures and not set(shared) & pictures
    assert listed - set(shared) <= pictures
    assert all(key in ALL_RESORTS and ALL_RESORTS[key].kind == "resort" for key in pictures)
    # Each is a small picture: the shape only, at most 320 px a side.
    assert all((root / "logos" / f"{key}.png").stat().st_size < 60_000 for key in pictures)
