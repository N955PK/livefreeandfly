"""The service worker is a real script: an empty one would install and leave the page with no offline copy."""
import re

from tahoe_snow.config import ROOT


def test_the_service_worker_names_its_cache_and_answers_requests():
    script = (ROOT / "sw.js").read_text()
    assert re.search(r"const VERSION = 'sierra-snow-v\d+';", script)
    assert "addEventListener('fetch'" in script or 'addEventListener("fetch"' in script
    assert len(script) > 5000


def test_every_regions_map_is_kept_for_offline_under_the_address_the_page_asks_for():
    page = (ROOT / "index.html").read_text()
    script = (ROOT / "sw.js").read_text()
    block = page[page.index("const REGIONS = {"):page.index("const REGION_PARTS")]
    found = re.findall(r'\n  (\w+): \{name: "[^"]+",.*?terrain: "(data/[\w-]+)", roads: "(data/[\w.-]+)"(.*?)\n', block)
    assert len(found) >= 46
    maps = script[script.index("const MAPS = ["):script.index("const MAP_STORE")]
    for key, terrain, roads, rest in found:
        rev = re.search(r'rev: "(\?v=\d+)"', rest)
        rev = rev.group(1) if rev else ""
        for name in (f"{terrain}.json", f"{terrain}.bin", roads):
            assert (ROOT / name).exists(), name
            assert f"'{name}{rev}'" in maps, (key, name, rev)
    # The maps live in a store of their own, which a new VERSION does not empty.
    assert "sierra-snow-maps" in script and not "sierra-snow-maps".startswith("sierra-snow-v")
