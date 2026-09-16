"""Minimal pcap (libpcap, Ethernet/IPv4) reader for OnFlight bench captures — no scapy dependency."""

import struct
from collections import defaultdict
from dataclasses import dataclass

PCAP_MAGIC_US = (0xA1B2C3D4, 0xD4C3B2A1)
PCAP_MAGIC_NS = (0xA1B23C4D, 0x4D3CB2A1)
ETH_IPV4 = 0x0800
PROTO_UDP = 17
PROTO_TCP = 6


@dataclass(frozen=True)
class Packet:
    t: float
    proto: int
    src: str
    dst: str
    sport: int
    dport: int
    payload: bytes


def _ip(b):
    return ".".join(str(x) for x in b)


def read_pcap(path):
    """Yield :class:`Packet` for every IPv4 UDP/TCP packet in a libpcap file."""
    with open(path, "rb") as fh:
        gh = fh.read(24)
        (magic,) = struct.unpack("<I", gh[:4])
        if magic in PCAP_MAGIC_US or magic in PCAP_MAGIC_NS:
            endian = "<" if magic in (0xA1B2C3D4, 0xA1B23C4D) else ">"
        else:
            raise ValueError(f"not a libpcap file: magic {magic:#x}")
        ns = magic in PCAP_MAGIC_NS
        while True:
            ph = fh.read(16)
            if len(ph) < 16:
                return
            ts_sec, ts_frac, incl_len, _ = struct.unpack(endian + "IIII", ph)
            frame = fh.read(incl_len)
            t = ts_sec + ts_frac / (1e9 if ns else 1e6)
            if len(frame) < 34 or struct.unpack("!H", frame[12:14])[0] != ETH_IPV4:
                continue
            ip = frame[14:]
            ihl = (ip[0] & 0x0F) * 4
            proto = ip[9]
            src, dst = _ip(ip[12:16]), _ip(ip[16:20])
            l4 = ip[ihl:]
            if proto == PROTO_UDP and len(l4) >= 8:
                sport, dport, ulen = struct.unpack("!HHH", l4[:6])
                yield Packet(t, proto, src, dst, sport, dport, l4[8:ulen])
            elif proto == PROTO_TCP and len(l4) >= 20:
                sport, dport = struct.unpack("!HH", l4[:4])
                data_off = ((l4[12] >> 4) & 0x0F) * 4
                yield Packet(t, proto, src, dst, sport, dport, l4[data_off:])


def group_flows(packets):
    """Group packets by (proto, src, dst, dport)."""
    flows = defaultdict(list)
    for p in packets:
        flows[(p.proto, p.src, p.dst, p.dport)].append(p)
    return flows


def constant_byte_mask(payloads):
    """Return a list of (index, value) for byte positions identical across all payloads."""
    if not payloads:
        return []
    n = min(len(p) for p in payloads)
    first = payloads[0]
    return [(i, first[i]) for i in range(n) if all(p[i] == first[i] for p in payloads)]
