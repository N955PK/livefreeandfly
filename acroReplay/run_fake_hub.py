#!/usr/bin/env python3
"""Pretend to be the OnFlight Hub: send recorded INS frames over UDP at their original pace.

    python run_fake_hub.py --dest 192.168.1.255 --replay captures/x/moving.pcap  # LAN broadcast
    python run_fake_hub.py --dest 192.168.1.255 --replay captures/x/moving.pcap  # LAN broadcast

Defaults to loopback, which the iOS simulator shares with this Mac.
"""

import argparse
import asyncio
import socket

from bridge.sources import replay_frames
from onflight.udp_ins import INS_PORT

DEFAULT_REPLAY = "tests/fixtures/udp2000_moving.bin"


async def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--replay", default=DEFAULT_REPLAY, help=".bin records file or .pcap (default: moving fixture)")
    ap.add_argument("--dest", default="127.0.0.1", help="destination address (default loopback)")
    ap.add_argument("--port", type=int, default=INS_PORT)
    ap.add_argument("--speed", type=float, default=1.0)
    args = ap.parse_args()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    print(f"sending {args.replay} → {args.dest}:{args.port} at x{args.speed} (Ctrl-C to stop)")
    sent = 0
    async for _, payload in replay_frames(args.replay, args.speed):
        sock.sendto(payload, (args.dest, args.port))
        sent += 1
        if sent % 500 == 0:
            print(f"  {sent} frames")


if __name__ == "__main__":
    asyncio.run(main())
