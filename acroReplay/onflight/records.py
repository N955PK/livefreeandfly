"""Timestamped-record files written by the capture kit: repeated ``<dH`` (unix time, length) + payload."""

import struct

RECORD_HEADER = struct.Struct("<dH")


def iter_records(path):
    """Yield ``(unix_time, payload)`` from a ``*.bin`` capture or fixture file."""
    with open(path, "rb") as fh:
        while True:
            head = fh.read(RECORD_HEADER.size)
            if len(head) < RECORD_HEADER.size:
                return
            t, n = RECORD_HEADER.unpack(head)
            yield t, fh.read(n)


def write_records(path, records):
    """Write ``(unix_time, payload)`` pairs in the capture-kit record format."""
    with open(path, "wb") as fh:
        for t, payload in records:
            fh.write(RECORD_HEADER.pack(t, len(payload)) + payload)
