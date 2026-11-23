"""Every avalanche zone's forecast in one file, so the page can keep them all on the phone for when there is no signal.

The page reads the avalanche centers as it needs them, which leaves a zone nobody opened with nothing saved. This
gathers, for each center the page's regions use, exactly what the page would ask for (the center's zones, each zone's
forecast, and the mountain weather write-up a forecast names) and writes them into one file keyed by the address the
page asks at. The page fetches the file when it opens with a signal and swaps it in for whatever it had saved.

The file also lists the photographs the page shows for those forecasts (each problem's photo and the first few of the
forecast's own), so the page can save those too. The file is rewritten only when a forecast has changed.
Standard library only.
python -m tahoe_snow.avybundle OUT_DIR
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

from tahoe_snow import config

API = "https://api.avalanche.org/v2/public"
CENTERS = config.avalanche_centers()
GALLERY = 8  # how many of a forecast's own photographs the page shows and saves; keep in step with AVY_GALLERY on the page


def get(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": "sierra-snow"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def photos_of(product: dict) -> list[str]:
    """The photographs the page shows for a forecast, at the size it shows them."""
    found = []
    for problem in product.get("forecast_avalanche_problems") or []:
        media = problem.get("media") or {}
        if media.get("type") == "image" and (media.get("url") or {}).get("thumbnail"):
            found.append(media["url"]["thumbnail"])
    shots = [m["url"]["thumbnail"] for m in product.get("media") or [] if m.get("type") == "image" and (m.get("url") or {}).get("thumbnail")]
    return list(dict.fromkeys(found + shots[:GALLERY]))


def gather(fetch=None) -> dict:
    """{"entries": {address: answer}, "photos": [addresses]}; a center or zone that cannot be read is left out."""
    fetch = fetch or get
    entries, photos = {}, []
    for center in CENTERS:
        url = f"{API}/products/map-layer/{center}"
        try:
            layer = fetch(url)
        except Exception as error:
            print(f"{center}: {error}")
            continue
        entries[url] = layer
        for feature in layer.get("features") or []:
            url = f"{API}/product?type=forecast&center_id={center}&zone_id={feature['id']}"
            try:
                product = fetch(url)
            except Exception as error:
                print(f"{center} zone {feature['id']}: {error}")
                continue
            entries[url] = product
            photos += photos_of(product)
            weather = (product.get("weather_data") or {}).get("weather_product_id")
            if weather:
                try:
                    entries[f"{API}/product/{weather}"] = fetch(f"{API}/product/{weather}")
                except Exception as error:
                    print(f"{center} weather {weather}: {error}")
    return {"entries": entries, "photos": list(dict.fromkeys(photos))}


def main(out_dir: str) -> int:
    path = os.path.join(out_dir, "bundle.json")
    found = gather()
    if not found["entries"]:
        print("Nothing could be read; the last file is left as it is.")
        return 1
    try:
        with open(path) as handle:
            last = json.load(handle)
    except (FileNotFoundError, ValueError):
        last = {}
    if last.get("entries") == found["entries"] and last.get("photos") == found["photos"]:
        print("No forecast has changed.")
        return 0
    os.makedirs(out_dir, exist_ok=True)
    with open(path, "w") as handle:
        json.dump({"built": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), **found}, handle, separators=(",", ":"))
    print(f"{len(found['entries'])} answers and {len(found['photos'])} photographs listed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
