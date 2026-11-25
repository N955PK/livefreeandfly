"""Airport forecasts (TAF) and reports (METAR) for the fog map, gathered where a browser cannot.

aviationweather.gov answers these requests but sends no CORS header, so the page cannot read them itself. The fog
collector (.github/workflows/fog-collect.yml) runs this every ten minutes and publishes the one file it writes, wx.json, as the only commit of the fog-wx branch,
which the page reads from raw.githubusercontent.com.

    python3 fog/wx.py OUT_DIR

The airports are the ones the page lists (AIRPORTS in fog/index.html), so there is one list to keep. A feed that fails
keeps what the last pass wrote for it, with the time it was read, and the page decides how old is too old.
"""
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

PAGE = Path(__file__).with_name("index.html")
API = "https://aviationweather.gov/api/data/{kind}?ids={ids}&format=json"
METAR_KEEP = ("icaoId", "obsTime", "temp", "dewp", "wdir", "wspd", "wgst", "visib", "wxString", "rawOb", "clouds")
TAF_KEEP = ("icaoId", "issueTime", "validTimeFrom", "validTimeTo", "rawTAF", "fcsts")


def airports():
    """The ids of the page's airports that report weather."""
    block = re.search(r"const AIRPORTS=\[(.*?)\n\];", PAGE.read_text(encoding="utf-8"), re.S).group(1)
    return [m.group(1) for m in re.finditer(r"\{id:'([A-Z0-9]{3,4})'([^}]*)\}", block) if "noWx" not in m.group(2)]


def fetch(kind, ids):
    request = urllib.request.Request(API.format(kind=kind, ids=",".join(ids)), headers={"User-Agent": "fog-wx-collector"})
    with urllib.request.urlopen(request, timeout=30) as response:
        rows = json.load(response)
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"no {kind} rows")
    return rows


def main(out_dir):
    out = Path(out_dir) / "wx.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        wx = json.loads(out.read_text())
    except (OSError, ValueError):
        wx = {}
    ids = airports()
    failed = 0
    for kind, keep in (("taf", TAF_KEEP), ("metar", METAR_KEEP)):
        try:
            rows = fetch(kind, ids)
        except Exception as error:  # one feed failing must not lose the other, or what was read last pass
            print(f"{kind}: {error}", file=sys.stderr)
            failed += 1
            continue
        wx[kind] = [{k: row[k] for k in keep if row.get(k) is not None} for row in rows]
        wx[kind + "At"] = int(time.time())
    out.write_text(json.dumps(wx, separators=(",", ":")))
    print(f"{len(ids)} airports: {len(wx.get('taf', []))} TAFs, {len(wx.get('metar', []))} METARs, {out.stat().st_size} bytes")
    return 1 if failed == 2 else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
