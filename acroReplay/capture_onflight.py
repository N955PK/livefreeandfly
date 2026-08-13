#!/usr/bin/env python3
"""Capture everything the OnFlight Hub exposes on its Wi-Fi network.

Run this while your Mac is connected to the "OnFlight Hub" Wi-Fi network
(SSID may have the unit serial appended). The Hub has no internet uplink,
so expect to be offline while this runs.

    python3 capture_onflight.py            # full capture (needs sudo for tcpdump)
    python3 capture_onflight.py --iface en0 --seconds 60

What it does:
  1. Mirrors the config webpage at 192.168.23.1 (HTML + JS/CSS assets) and
     probes any API endpoints referenced in the page's JavaScript, sampling
     JSON endpoints twice to show which fields are live.
  2. Records all UDP traffic with tcpdump in two phases:
       - stationary: leave the Hub flat and still
       - moving: slowly roll / pitch / yaw the Hub by hand
     The known-truth stationary values and the hand-motion signatures are
     what let us map the binary payload fields afterward.
  3. Saves network metadata (interface config, ARP table) for context.

Everything lands in captures/<timestamp>/. When it finishes, reconnect to
normal Wi-Fi and hand the directory to Claude for decoding.
"""

import argparse
import datetime
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HUB_IP = "192.168.23.1"
BASE_URL = f"http://{HUB_IP}"
HTTP_TIMEOUT = 4
ENDPOINT_GUESSES = [
    "/data", "/data.json", "/json", "/status", "/status.json", "/config",
    "/config.json", "/api", "/api/data", "/api/status", "/live", "/stream",
    "/hub", "/hubdata", "/telemetry", "/version",
]


def http_get(path):
    url = BASE_URL + path if path.startswith("/") else path
    req = urllib.request.Request(url, headers={"User-Agent": "onflight-capture"})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return resp.status, resp.headers.get("Content-Type", ""), resp.read()


def wait_for_hub(max_wait=90):
    print(f"Looking for the Hub at {BASE_URL} ...")
    deadline = time.monotonic() + max_wait
    while time.monotonic() < deadline:
        try:
            status, _, _ = http_get("/")
            print(f"  Hub is up (HTTP {status}).")
            return True
        except (urllib.error.URLError, OSError):
            print("  Not reachable yet - is this Mac on the 'OnFlight Hub' Wi-Fi? Retrying...")
            time.sleep(5)
    return False


def sanitize(path):
    return re.sub(r"[^A-Za-z0-9._-]", "_", path.strip("/")) or "index"


def mirror_webpage(outdir):
    webdir = outdir / "web"
    webdir.mkdir(parents=True, exist_ok=True)
    fetched = {}

    status, ctype, body = http_get("/")
    (webdir / "index.html").write_bytes(body)
    fetched["/"] = {"status": status, "content_type": ctype, "bytes": len(body)}
    text = body.decode("utf-8", errors="replace")

    assets = set(re.findall(r"""(?:src|href)=["']([^"']+)["']""", text))
    asset_texts = [text]
    for asset in sorted(assets):
        if asset.startswith(("http://", "https://")) and HUB_IP not in asset:
            continue
        path = "/" + asset.lstrip("/")
        try:
            status, ctype, body = http_get(path)
        except (urllib.error.URLError, OSError) as exc:
            fetched[path] = {"error": str(exc)}
            continue
        (webdir / sanitize(path)).write_bytes(body)
        fetched[path] = {"status": status, "content_type": ctype, "bytes": len(body)}
        if any(k in ctype for k in ("javascript", "html", "json", "text")):
            asset_texts.append(body.decode("utf-8", errors="replace"))

    candidates = set(ENDPOINT_GUESSES)
    for t in asset_texts:
        candidates.update(re.findall(r"""["'](/[A-Za-z0-9_./-]{2,40})["']""", t))
        candidates.update(re.findall(r"""(?:fetch|open|WebSocket|EventSource)\(\s*["']([^"']+)["']""", t))

    probes = {}
    for path in sorted(candidates):
        if not path.startswith("/") or path in fetched:
            continue
        entry = {}
        for attempt in ("sample1", "sample2"):
            try:
                status, ctype, body = http_get(path)
                fname = f"probe_{sanitize(path)}_{attempt}"
                (webdir / fname).write_bytes(body)
                entry[attempt] = {"status": status, "content_type": ctype, "bytes": len(body), "file": fname}
            except (urllib.error.URLError, OSError) as exc:
                entry[attempt] = {"error": str(exc)}
                break
            time.sleep(1.0)
        probes[path] = entry

    (webdir / "manifest.json").write_text(json.dumps({"fetched": fetched, "probes": probes}, indent=2))
    ok = [p for p, e in probes.items() if e.get("sample1", {}).get("status") == 200]
    print(f"  Mirrored {len(fetched)} page assets, probed {len(probes)} endpoint candidates, {len(ok)} responded 200:")
    for p in ok:
        print(f"    {p}")


def run_tcpdump(iface, outfile, seconds, label):
    print(f"\n=== UDP capture: {label} ({seconds}s) ===")
    if label == "stationary":
        print("Leave the Hub powered on, flat, and completely still.")
    else:
        print("Pick up the Hub and SLOWLY roll, pitch, and yaw it, one axis at a time.")
        print("  Suggested: ~20s of roll rocking, ~20s of pitch rocking, ~20s of yaw twisting.")
    input("Press Enter to start this phase... ")
    cmd = ["sudo", "tcpdump", "-i", iface, "-w", str(outfile), "-s", "0", "udp"]
    print("  " + " ".join(cmd))
    proc = subprocess.Popen(cmd)
    try:
        time.sleep(seconds)
    finally:
        subprocess.run(["sudo", "kill", "-INT", str(proc.pid)], check=False)
        proc.wait(timeout=10)
    size = outfile.stat().st_size if outfile.exists() else 0
    print(f"  Wrote {outfile.name}: {size:,} bytes")
    if size < 1000:
        print("  WARNING: capture is nearly empty - check the interface name (--iface).")


def save_metadata(outdir, iface):
    meta = {"captured_at": datetime.datetime.now().astimezone().isoformat(), "iface": iface}
    for name, cmd in [
        ("ifconfig", ["ifconfig", iface]),
        ("arp", ["arp", "-a"]),
        ("wifi", ["networksetup", "-getairportnetwork", iface]),
    ]:
        try:
            meta[name] = subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout
        except (OSError, subprocess.TimeoutExpired) as exc:
            meta[name] = f"error: {exc}"
    (outdir / "metadata.json").write_text(json.dumps(meta, indent=2))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--iface", default="en0", help="Wi-Fi interface (default en0)")
    ap.add_argument("--seconds", type=int, default=60, help="seconds per tcpdump phase (default 60)")
    ap.add_argument("--skip-udp", action="store_true", help="only mirror the webpage, skip tcpdump")
    args = ap.parse_args()

    if not shutil.which("tcpdump") and not args.skip_udp:
        sys.exit("tcpdump not found - it ships with macOS, so check PATH, or use --skip-udp.")

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    outdir = Path(__file__).parent / "captures" / stamp
    outdir.mkdir(parents=True, exist_ok=True)
    print(f"Output: {outdir}\n")

    if not wait_for_hub():
        sys.exit("Gave up waiting for the Hub. Join its Wi-Fi network and rerun.")

    save_metadata(outdir, args.iface)
    print("\n=== Mirroring config webpage ===")
    mirror_webpage(outdir)

    if not args.skip_udp:
        run_tcpdump(args.iface, outdir / "udp_stationary.pcap", args.seconds, "stationary")
        run_tcpdump(args.iface, outdir / "udp_moving.pcap", args.seconds, "moving")

    print("\nDone. Reconnect to your normal Wi-Fi and point Claude at:")
    print(f"  {outdir}")


if __name__ == "__main__":
    main()
