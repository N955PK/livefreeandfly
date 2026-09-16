"""Where INS frames come from: the Hub's live UDP broadcast, or a recording played back at wall-clock pace.

Both are async generators of ``(wall_time, payload)`` with the raw 67-byte frame, so the
server decodes and logs exactly the same bytes either way.
"""

import asyncio
import socket
import time

from onflight.pcap import read_pcap
from onflight.records import iter_records
from onflight.udp_ins import INS_PORT, INS_SIZE


class _Collector(asyncio.DatagramProtocol):
    def __init__(self, queue):
        self.queue = queue

    def datagram_received(self, data, addr):
        if len(data) == INS_SIZE:
            self.queue.put_nowait((time.time(), data))


async def live_frames(port=INS_PORT):
    """Yield INS frames broadcast by the Hub (requires being on the Hub's Wi-Fi network)."""
    loop = asyncio.get_running_loop()
    queue = asyncio.Queue()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind(("", port))
    transport, _ = await loop.create_datagram_endpoint(lambda: _Collector(queue), sock=sock)
    try:
        while True:
            yield await queue.get()
    finally:
        transport.close()


def recorded_frames(path):
    """``(time, payload)`` INS frames from a capture-kit ``.bin`` records file or a ``.pcap``."""
    path = str(path)
    if path.endswith(".pcap"):
        return [(p.t, p.payload) for p in read_pcap(path) if p.proto == 17 and p.dport == INS_PORT]
    return [(t, p) for t, p in iter_records(path) if len(p) == INS_SIZE]


async def replay_frames(path, speed=1.0, repeat=True):
    """Yield recorded INS frames with their original spacing (scaled by ``speed``), looping if ``repeat``."""
    frames = recorded_frames(path)
    if not frames:
        raise ValueError(f"no INS frames in {path}")
    while True:
        wall0, t0 = time.time(), frames[0][0]
        for t, payload in frames:
            delay = wall0 + (t - t0) / speed - time.time()
            if delay > 0:
                await asyncio.sleep(delay)
            yield time.time(), payload
        if not repeat:
            return
