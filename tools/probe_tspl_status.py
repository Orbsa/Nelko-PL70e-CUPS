#!/usr/bin/env python3
"""Probe standard TSPL/TSPL2 status queries.

These are documented TSPL2 status-poll commands that should not trigger any
physical side effects (no print, no paper feed). We try each on each candidate
write channel and watch all notify/indicate channels for replies.
"""

import asyncio
from datetime import datetime

from bleak import BleakClient

ADDRESS = "DC:0D:30:5A:A7:F5"

WRITE_PIPES = [
    ("0000fec7-0000-1000-8000-00805f9b34fb", "fec7"),
    ("0000fff2-0000-1000-8000-00805f9b34fb", "fff2"),
    ("49535343-8841-43f4-a8d4-ecbe34729bb3", "issc_tx"),
]

NOTIFY_PIPES = [
    ("0000fff1-0000-1000-8000-00805f9b34fb", "fff1"),
    ("0000fec8-0000-1000-8000-00805f9b34fb", "fec8"),
    ("49535343-1e4d-4bd9-ba61-23c647249616", "issc_rx"),
    ("49535343-aca3-481c-91ec-d85e28a60318", "issc_ctl"),
]

# Standard TSPL2 status queries (no side effects).
QUERIES = [
    (b"\x1b!?", "ESC!? readiness"),
    (b"\x1b!o\r\n", "ESC!o cancel-pause/status"),
    (b"\x1b!R\r\n", "ESC!R reset-status"),
    (b"\x1bM\r\n", "ESC M (older status)"),
    (b"~!T\r\n", "~!T RTC"),
    (b"~!I\r\n", "~!I codepage"),
    (b"~!F\r\n", "~!F paper"),
    (b"~!@\r\n", "~!@ idle/sleep"),
]


def ts():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def cb(label):
    def _(_s, d):
        print(f"  [{ts()}] <- {label:8s} hex={bytes(d).hex()}  ascii={bytes(d)!r}")
    return _


async def main():
    async with BleakClient(ADDRESS) as client:
        print(f"Connected: {client.is_connected}")
        for uuid, label in NOTIFY_PIPES:
            try:
                await client.start_notify(uuid, cb(label))
            except Exception as e:
                print(f"  subscribe {label}: {e}")
        await asyncio.sleep(0.3)  # let initial handshake settle

        for cmd, name in QUERIES:
            for uuid, label in WRITE_PIPES:
                print(f"[{ts()}] --- {name} via {label} ---")
                try:
                    await client.write_gatt_char(uuid, cmd, response=True)
                except Exception as e:
                    print(f"    write {label} FAILED: {e}")
                await asyncio.sleep(0.6)


if __name__ == "__main__":
    asyncio.run(main())
