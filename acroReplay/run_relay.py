#!/usr/bin/env python3
"""Forward the Hub's broadcast INS stream to a phone by unicast.

iOS only delivers UDP *broadcast* to apps that hold Apple's multicast entitlement. Until that is
granted, run this on a Mac that is on the Hub's Wi-Fi and point it at the phone (also on that
Wi-Fi): every 67-byte frame the Hub broadcasts on port 2000 is re-sent unicast to the phone, which
WingRock receives without any entitlement.

    python run_relay.py 192.168.23.7          # the phone's address on the Hub network
"""

import argparse
import socket
import time

from onflight.udp_ins import INS_PORT, INS_SIZE


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("phone", help="phone IP on the Hub's Wi-Fi (Settings → Wi-Fi → the network's ⓘ)")
    ap.add_argument("--port", type=int, default=INS_PORT)
    args = ap.parse_args()
    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    rx.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    rx.bind(("", args.port))
    tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print(f"relaying Hub frames from :{args.port} → {args.phone}:{args.port}  (Ctrl-C to stop)")
    n, last = 0, time.time()
    while True:
        data, _ = rx.recvfrom(2048)
        if len(data) != INS_SIZE:
            continue
        tx.sendto(data, (args.phone, args.port))
        n += 1
        if time.time() - last >= 10:
            print(f"  {n} frames relayed")
            last = time.time()


if __name__ == "__main__":
    main()
