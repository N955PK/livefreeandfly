#!/usr/bin/env python3
"""Run the acroReplay bridge: Hub UDP (or a recording) in, WebSocket + web app out.

    python run_bridge.py                                  # live: listen for the Hub's broadcast
    python run_bridge.py --replay captures/.../moving.pcap
    python run_bridge.py --replay tests/fixtures/udp2000_moving.bin --speed 0.5

Then open http://<this machine>:8645/ on any device on the same network.
"""

import argparse
import logging
import socket

from aiohttp import web

from bridge.server import make_app
from bridge.sources import live_frames, replay_frames

DEFAULT_PORT = 8645


def lan_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.168.23.1", 1))
            return s.getsockname()[0]
    except OSError:
        return "localhost"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--replay", metavar="PATH", help="play a .bin records file or .pcap instead of listening live")
    ap.add_argument("--speed", type=float, default=1.0, help="replay speed factor (default 1.0)")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--ground-ft", type=float, default=163.0,
                    help="ground elevation at the origin, ft MSL (default 163 = KWVI)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

    source = replay_frames(args.replay, args.speed) if args.replay else live_frames()
    log = logging.getLogger("bridge")
    log.info("source: %s", f"replay {args.replay} x{args.speed}" if args.replay else "live UDP")
    log.info("open http://%s:%d/ (this machine) or http://localhost:%d/", lan_ip(), args.port, args.port)
    web.run_app(make_app(source, args.ground_ft), host=args.host, port=args.port, print=None)


if __name__ == "__main__":
    main()
