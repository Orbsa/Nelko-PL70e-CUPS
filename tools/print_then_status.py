#!/usr/bin/env python3
"""Send the TSPL dot job and follow it with \\x1b!? to confirm the channel is alive."""

import argparse
import asyncio
from datetime import datetime

from bleak import BleakClient

ADDRESS = "DC:0D:30:5A:A7:F5"

WRITE_CHANNELS = {
    "fec7": "0000fec7-0000-1000-8000-00805f9b34fb",
    "fff2": "0000fff2-0000-1000-8000-00805f9b34fb",
    "issc": "49535343-8841-43f4-a8d4-ecbe34729bb3",
}

NOTIFY_CHANNELS = [
    ("0000fff1-0000-1000-8000-00805f9b34fb", "fff1"),
    ("0000fec8-0000-1000-8000-00805f9b34fb", "fec8"),
    ("49535343-1e4d-4bd9-ba61-23c647249616", "issc_rx"),
    ("49535343-aca3-481c-91ec-d85e28a60318", "issc_ctl"),
]

DPI = 203
DOTS_PER_MM = DPI / 25.4


def ts():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def cb(label):
    def _(_s, d):
        print(f"  [{ts()}] <- {label:8s} hex={bytes(d).hex()}  ascii={bytes(d)!r}")
    return _


def build_tspl(x_mm, y_mm, dot_mm):
    x = round(x_mm * DOTS_PER_MM)
    y = round(y_mm * DOTS_PER_MM)
    s = round(dot_mm * DOTS_PER_MM)
    return (
        b"SIZE 100 mm,150 mm\r\n"
        b"GAP 2 mm,0 mm\r\n"
        b"DENSITY 8\r\n"
        b"SPEED 4\r\n"
        b"DIRECTION 0,0\r\n"
        b"CLS\r\n"
        + f"BAR {x},{y},{s},{s}\r\n".encode()
        + b"PRINT 1,1\r\n"
    )


async def write_chunked(client, uuid, data, *, response, chunk, gap_ms=10):
    for i in range(0, len(data), chunk):
        await client.write_gatt_char(uuid, data[i:i + chunk], response=response)
        if gap_ms:
            await asyncio.sleep(gap_ms / 1000)


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--channel", choices=list(WRITE_CHANNELS), default="fff2")
    p.add_argument("--with-response", action="store_true")
    p.add_argument("--chunk", type=int, default=20)
    p.add_argument("--x", type=float, default=50.0)
    p.add_argument("--y", type=float, default=75.0)
    p.add_argument("--size", type=float, default=4.0)
    p.add_argument("--gap-ms", type=int, default=10)
    args = p.parse_args()

    payload = build_tspl(args.x, args.y, args.size)
    uuid = WRITE_CHANNELS[args.channel]
    use_response = args.with_response or args.channel == "fec7"

    print(f"--- TSPL ({len(payload)}B) ---")
    print(payload.decode().strip())
    print("--- end ---")

    async with BleakClient(ADDRESS) as client:
        print(f"[{ts()}] Connected (mtu={client.mtu_size}); subscribing")
        for u, label in NOTIFY_CHANNELS:
            try:
                await client.start_notify(u, cb(label))
            except Exception as e:
                print(f"  subscribe {label}: {e}")
        await asyncio.sleep(0.3)

        print(f"[{ts()}] -> TSPL via {args.channel} response={use_response} chunk={args.chunk}")
        await write_chunked(client, uuid, payload, response=use_response,
                            chunk=args.chunk, gap_ms=args.gap_ms)

        print(f"[{ts()}] -> status query \\x1b!? via same channel")
        await client.write_gatt_char(uuid, b"\x1b!?", response=use_response)

        print(f"[{ts()}] listening 3s")
        await asyncio.sleep(3.0)


if __name__ == "__main__":
    asyncio.run(main())
