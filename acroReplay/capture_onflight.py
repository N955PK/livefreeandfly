#!/usr/bin/env python3
"""Capture everything the OnFlight Hub exposes on its Wi-Fi network (v2).

Run from a Mac near the Hub. The script joins (and re-joins) the Hub's Wi-Fi
itself, so start it from any network; the Mac is offline while it runs.

    python3 capture_onflight.py                       # full capture
    python3 capture_onflight.py --seconds 90          # longer phases
    python3 capture_onflight.py --ssid "OnFlight Hub XXXX" --iface en1

Per run it records, under captures/<timestamp>/:
  web/           config page mirror + GET /config, /sys-config, /sensor-config, /ins-config
  <phase>.pcap   ALL traffic on the Wi-Fi interface (tcpdump; finds any UDP stream)
  ws_data_<phase>.bin   raw ws://hub/data frames  (records: <dH> unix-time, len, payload)
  gdl90_<phase>.bin     UDP datagrams arriving on the GDL90 port (same record format)
  metadata.json

Two phases: "stationary" (Hub flat and still) and "moving" (slow hand
roll / pitch / yaw, one axis at a time). During each phase the script also
broadcasts ForeFlight's discovery JSON on UDP 63093 so a Hub that unicasts to
discovered EFB clients will start sending to this Mac.

Why v2: the 2026-09-15 run lost the Hub Wi-Fi mid-capture (macOS auto-joined a
network with internet) and probing unknown URLs hung the Hub's web server, so
this version re-asserts the SSID before every step and only touches known paths.
"""

import argparse
import base64
import datetime
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

HUB_IP = "192.168.23.1"
HUB_SUBNET = "192.168.23."
BASE_URL = f"http://{HUB_IP}"
HTTP_TIMEOUT = 5
DEFAULT_SSID = "OnFlight Hub 4496A6FE8CE0"
CONFIG_PATHS = ["/config", "/sys-config", "/sensor-config", "/ins-config"]
PAGE_ASSETS = ["/", "/script.js", "/style.css"]
FOREFLIGHT_DISCOVERY_PORT = 63093
GDL90_PORT = 4000
RECORD_HEADER = struct.Struct("<dH")
WS_PITCH_ROLL = struct.Struct("<hh")


# ---------------------------------------------------------------- Wi-Fi ----
def current_ip(iface):
    out = subprocess.run(["ipconfig", "getifaddr", iface], capture_output=True, text=True).stdout.strip()
    return out


def ensure_wifi(iface, ssid, wait_s=45):
    """Make sure the interface has a Hub-subnet address, (re)joining the SSID if needed."""
    ip = current_ip(iface)
    if ip.startswith(HUB_SUBNET):
        return ip
    print(f"  Joining Wi-Fi '{ssid}' on {iface} ...")
    subprocess.run(["networksetup", "-setairportnetwork", iface, ssid], capture_output=True, text=True)
    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline:
        ip = current_ip(iface)
        if ip.startswith(HUB_SUBNET):
            print(f"  Connected, {iface} = {ip}")
            return ip
        time.sleep(1)
    sys.exit(f"Could not get a {HUB_SUBNET}x address on {iface}. Is the Hub powered on? Is the SSID '{ssid}'?")


# ----------------------------------------------------------------- HTTP ----
def http_get(path):
    req = urllib.request.Request(BASE_URL + path, headers={"User-Agent": "onflight-capture"})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return resp.status, resp.headers.get("Content-Type", ""), resp.read()


def mirror_web(outdir):
    webdir = outdir / "web"
    webdir.mkdir(parents=True, exist_ok=True)
    summary = {}
    for path in PAGE_ASSETS + CONFIG_PATHS:
        name = "index.html" if path == "/" else path.strip("/").replace("/", "_")
        if path in CONFIG_PATHS:
            name += ".json"
        try:
            status, ctype, body = http_get(path)
            (webdir / name).write_bytes(body)
            summary[path] = {"status": status, "content_type": ctype, "bytes": len(body)}
            if path == "/config":
                cfg = json.loads(body)
                print(f"  /config: firmware {cfg.get('version')}, hw {cfg.get('hw-version')}, "
                      f"serial {cfg.get('serial'):X}, product {cfg.get('product')}, "
                      f"datalog-format {cfg.get('datalog-format')}, datalog-srd {cfg.get('datalog-srd')}")
        except (urllib.error.URLError, OSError, ValueError) as exc:
            summary[path] = {"error": str(exc)}
            print(f"  {path}: {exc}")
    (webdir / "manifest.json").write_text(json.dumps(summary, indent=2))


# ------------------------------------------------------------ WebSocket ----
def recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("websocket closed")
        buf += chunk
    return buf


def ws_connect(host, path):
    sock = socket.create_connection((host, 80), timeout=5)
    key = base64.b64encode(os.urandom(16)).decode()
    request = (f"GET {path} HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\nOrigin: http://{host}\r\n\r\n")
    sock.sendall(request.encode())
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("no websocket handshake response")
        buf += chunk
    head, leftover = buf.split(b"\r\n\r\n", 1)
    if b" 101 " not in head.split(b"\r\n")[0]:
        raise ConnectionError(f"websocket upgrade refused: {head[:120]!r}")
    return sock, leftover


def ws_send(sock, opcode, payload=b""):
    mask = os.urandom(4)
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    header = bytes([0x80 | opcode, 0x80 | len(payload)])
    sock.sendall(header + mask + masked)


def ws_frames(sock, leftover, deadline):
    """Yield (opcode, payload) until deadline; answers pings; stops on close."""
    pending = leftover

    def take(n):
        nonlocal pending
        while len(pending) < n:
            pending += recv_exact(sock, n - len(pending))
        out, pending = pending[:n], pending[n:]
        return out

    while time.time() < deadline:
        sock.settimeout(max(0.1, deadline - time.time()))
        try:
            b0, b1 = take(2)
        except socket.timeout:
            return
        opcode = b0 & 0x0F
        length = b1 & 0x7F
        if length == 126:
            (length,) = struct.unpack(">H", take(2))
        elif length == 127:
            (length,) = struct.unpack(">Q", take(8))
        mask = take(4) if b1 & 0x80 else None
        payload = take(length)
        if mask:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        if opcode == 0x9:
            ws_send(sock, 0xA, payload)
        elif opcode == 0x8:
            return
        else:
            yield opcode, payload


def log_websocket(outfile, seconds):
    """Record ws://hub/data frames for `seconds`; returns (count, first_payload, last_payload)."""
    deadline = time.time() + seconds
    count, first, last = 0, None, None
    with open(outfile, "wb") as fh:
        while time.time() < deadline:
            try:
                sock, leftover = ws_connect(HUB_IP, "/data")
            except OSError as exc:
                print(f"  websocket connect failed ({exc}); retrying in 2 s")
                time.sleep(2)
                continue
            try:
                for opcode, payload in ws_frames(sock, leftover, deadline):
                    if opcode != 0x2:
                        continue
                    fh.write(RECORD_HEADER.pack(time.time(), len(payload)) + payload)
                    count += 1
                    last = payload
                    first = first or payload
            except (OSError, ConnectionError) as exc:
                print(f"  websocket dropped ({exc}); reconnecting")
            finally:
                sock.close()
    return count, first, last


def describe_frame(payload):
    if payload is None or len(payload) < 25:
        return "n/a"
    gnss = payload[14]
    pitch, roll = WS_PITCH_ROLL.unpack_from(payload, 21)
    return f"pitch {pitch / 100:+.2f}°, roll {roll / 100:+.2f}°, fix {gnss & 7}, sats {gnss >> 3}, {len(payload)} B"


# ------------------------------------------------------------------ UDP ----
class Gdl90Listener(threading.Thread):
    """Records datagrams on the GDL90 port and broadcasts ForeFlight discovery every 5 s."""

    def __init__(self, outfile, stop_event):
        super().__init__(daemon=True)
        self.outfile = outfile
        self.stop_event = stop_event
        self.count = 0
        self.sources = set()

    def run(self):
        rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        rx.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        rx.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        rx.bind(("", GDL90_PORT))
        rx.settimeout(0.5)
        tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        tx.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        discovery = json.dumps({"App": "ForeFlight", "GDL90": {"port": GDL90_PORT}}).encode()
        next_discovery = 0.0
        with open(self.outfile, "wb") as fh:
            while not self.stop_event.is_set():
                if time.time() >= next_discovery:
                    for dest in ("255.255.255.255", HUB_SUBNET + "255", HUB_IP):
                        try:
                            tx.sendto(discovery, (dest, FOREFLIGHT_DISCOVERY_PORT))
                        except OSError:
                            pass
                    next_discovery = time.time() + 5
                try:
                    data, addr = rx.recvfrom(4096)
                except socket.timeout:
                    continue
                fh.write(RECORD_HEADER.pack(time.time(), len(data)) + data)
                self.count += 1
                self.sources.add(addr[0])
        rx.close()
        tx.close()


def start_tcpdump(iface, outfile):
    cmd = ["sudo", "tcpdump", "-i", iface, "-w", str(outfile), "-s", "0", "not arp"]
    return subprocess.Popen(cmd, stderr=subprocess.DEVNULL)


def stop_tcpdump(proc):
    subprocess.run(["sudo", "kill", "-INT", str(proc.pid)], check=False)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def run_phase(label, outdir, iface, ssid, seconds):
    print(f"\n=== Phase: {label} ({seconds}s) ===")
    if label == "stationary":
        print("Leave the Hub powered on, flat, and completely still.")
    else:
        print("Pick up the Hub and SLOWLY roll, pitch, and yaw it, one axis at a time.")
        print("  Suggested: ~20 s of roll rocking, ~20 s of pitch rocking, ~20 s of yaw twisting.")
    input("Press Enter to start this phase... ")
    ensure_wifi(iface, ssid)

    stop = threading.Event()
    gdl = Gdl90Listener(outdir / f"gdl90_{label}.bin", stop)
    pcap = outdir / f"{label}.pcap"
    dump = start_tcpdump(iface, pcap)
    time.sleep(1.5)
    gdl.start()
    count, first, last = log_websocket(outdir / f"ws_data_{label}.bin", seconds)
    stop.set()
    gdl.join(timeout=3)
    stop_tcpdump(dump)

    size = pcap.stat().st_size if pcap.exists() else 0
    print(f"  websocket frames: {count} (~{count / seconds:.1f} Hz)")
    print(f"    first: {describe_frame(first)}")
    print(f"    last:  {describe_frame(last)}")
    print(f"  GDL90-port datagrams: {gdl.count} from {sorted(gdl.sources) or 'nobody'}")
    print(f"  pcap: {size:,} bytes")
    if size < 2000:
        print("  WARNING: pcap is nearly empty - Wi-Fi may have dropped or tcpdump lacks permission.")
    if not current_ip(iface).startswith(HUB_SUBNET):
        print("  WARNING: Wi-Fi left the Hub network during this phase.")


def save_metadata(outdir, iface, ssid):
    meta = {"captured_at": datetime.datetime.now().astimezone().isoformat(), "iface": iface, "ssid": ssid}
    for name, cmd in [("ifconfig", ["ifconfig", iface]), ("summary", ["ipconfig", "getsummary", iface])]:
        try:
            meta[name] = subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout
        except (OSError, subprocess.TimeoutExpired) as exc:
            meta[name] = f"error: {exc}"
    (outdir / "metadata.json").write_text(json.dumps(meta, indent=2))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--iface", default="en0", help="Wi-Fi interface (default en0)")
    ap.add_argument("--ssid", default=DEFAULT_SSID, help=f"Hub SSID (default '{DEFAULT_SSID}')")
    ap.add_argument("--seconds", type=int, default=60, help="seconds per phase (default 60)")
    args = ap.parse_args()

    if not shutil.which("tcpdump"):
        sys.exit("tcpdump not found (it ships with macOS - check PATH).")
    print("Caching sudo credentials for tcpdump ...")
    if subprocess.run(["sudo", "-v"]).returncode != 0:
        sys.exit("sudo is required for tcpdump.")

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    outdir = Path(__file__).parent / "captures" / stamp
    outdir.mkdir(parents=True, exist_ok=True)
    print(f"Output: {outdir}\n")

    print("=== Wi-Fi ===")
    ensure_wifi(args.iface, args.ssid)
    save_metadata(outdir, args.iface, args.ssid)

    print("\n=== Config page + JSON config ===")
    mirror_web(outdir)

    for label in ("stationary", "moving"):
        run_phase(label, outdir, args.iface, args.ssid, args.seconds)

    print("\nDone. Reconnect to your normal Wi-Fi and point Claude at:")
    print(f"  {outdir}")


if __name__ == "__main__":
    main()
