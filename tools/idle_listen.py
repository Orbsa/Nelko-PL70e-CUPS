#!/usr/bin/env python3
"""Connect, subscribe to every notify/indicate channel, write nothing — just log."""

import asyncio
from datetime import datetime

from bleak import BleakClient

ADDRESS = "DC:0D:30:5A:A7:F5"
DURATION = 20.0

CHARS = {
    "0000fff1-0000-1000-8000-00805f9b34fb": "fff1",
    "0000fec8-0000-1000-8000-00805f9b34fb": "fec8",
    "49535343-1e4d-4bd9-ba61-23c647249616": "issc_rx",
    "49535343-aca3-481c-91ec-d85e28a60318": "issc_ctl",
}


def ts():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def cb(label):
    def _(_s, d):
        print(f"[{ts()}] {label:8s} hex={bytes(d).hex()}")
    return _


async def main():
    async with BleakClient(ADDRESS) as client:
        print(f"[{ts()}] Connected: {client.is_connected}")
        for uuid, label in CHARS.items():
            try:
                await client.start_notify(uuid, cb(label))
            except Exception as e:
                print(f"  subscribe {label}: {e}")
        print(f"[{ts()}] Idle listen for {DURATION}s...")
        await asyncio.sleep(DURATION)
        print(f"[{ts()}] Done.")


if __name__ == "__main__":
    asyncio.run(main())
