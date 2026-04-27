#!/usr/bin/env python3
"""Print a single dot at (x,y) mm on a 4x6" label, for iterative calibration.

The same label is meant to be re-fed manually between runs — each call clears
the canvas (CLS) but only prints a dot, so successive runs build up a dot grid
on the same physical label without wasting paper.

Usage:
  python dot_print.py 50 75               # dot at 50mm,75mm
  python dot_print.py 50 75 --size 3      # 3mm dot
  python dot_print.py 50 75 --channel fec7
"""

import argparse
import asyncio
import sys
from datetime import datetime

from bleak import BleakClient

ADDRESS = "DC:0D:30:5A:A7:F5"

WRITE_CHANNELS = {
    "fec7": ("0000fec7-0000-1000-8000-00805f9b34fb", True),   # write-with-response only
    "fff2": ("0000fff2-0000-1000-8000-00805f9b34fb", False),  # supports WNR
    "issc": ("49535343-8841-43f4-a8d4-ecbe34729bb3", False),  # supports WNR
}

NOTIFY_CHANNELS = [
    ("0000fff1-0000-1000-8000-00805f9b34fb", "fff1"),
    ("0000fec8-0000-1000-8000-00805f9b34fb", "fec8"),
    ("49535343-1e4d-4bd9-ba61-23c647249616", "issc_rx"),
    ("49535343-aca3-481c-91ec-d85e28a60318", "issc_ctl"),
]

DPI = 203
DOTS_PER_MM = DPI / 25.4  # ≈ 7.992


def ts():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def mm_to_dots(mm: float) -> int:
    return round(mm * DOTS_PER_MM)


def build_tspl(x_mm: float, y_mm: float, dot_mm: float,
               page_w_mm: float, page_h_mm: float,
               gap_mm: float, density: int, speed: int, copies: int) -> bytes:
    x = mm_to_dots(x_mm)
    y = mm_to_dots(y_mm)
    s = mm_to_dots(dot_mm)
    cmds = [
        f"SIZE {page_w_mm} mm,{page_h_mm} mm",
        f"GAP {gap_mm} mm,0 mm",
        f"DENSITY {density}",
        f"SPEED {speed}",
        "DIRECTION 0,0",
        "CLS",
        f"BAR {x},{y},{s},{s}",
        f"PRINT {copies}",
    ]
    return ("\r\n".join(cmds) + "\r\n").encode()


def make_cb(label):
    def _(_s, d):
        print(f"  [{ts()}] <- {label:8s} hex={bytes(d).hex()}")
    return _


async def stream(client, char_uuid: str, payload: bytes, *, response: bool, chunk: int):
    for i in range(0, len(payload), chunk):
        part = payload[i:i + chunk]
        await client.write_gatt_char(char_uuid, part, response=response)


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("x", type=float, help="dot x position in mm")
    p.add_argument("y", type=float, help="dot y position in mm")
    p.add_argument("--size", type=float, default=4.0, help="dot side length in mm (default 4)")
    p.add_argument("--page-w", type=float, default=100.0, help="page width mm (default 100)")
    p.add_argument("--page-h", type=float, default=150.0, help="page height mm (default 150)")
    p.add_argument("--gap", type=float, default=2.0, help="gap between labels in mm (default 2)")
    p.add_argument("--density", type=int, default=8, help="print density 1-15 (default 8)")
    p.add_argument("--speed", type=int, default=4, help="print speed (default 4)")
    p.add_argument("--copies", type=int, default=1)
    p.add_argument("--channel", choices=list(WRITE_CHANNELS), default="fff2",
                   help="GATT write channel (default fff2)")
    p.add_argument("--with-response", action="store_true",
                   help="force write-with-response on channels that support WNR")
    p.add_argument("--chunk", type=int, default=180, help="bytes per BLE write")
    p.add_argument("--listen-after", type=float, default=2.0,
                   help="seconds to keep notifications open after writing")
    p.add_argument("--dry-run", action="store_true", help="print TSPL bytes; don't connect")
    args = p.parse_args()

    payload = build_tspl(args.x, args.y, args.size,
                         args.page_w, args.page_h, args.gap,
                         args.density, args.speed, args.copies)
    print(f"--- TSPL ({len(payload)} bytes) ---")
    sys.stdout.write(payload.decode())
    print("--- end ---")
    if args.dry_run:
        return

    char_uuid, write_only = WRITE_CHANNELS[args.channel]
    use_response = True if write_only else args.with_response

    async with BleakClient(ADDRESS) as client:
        print(f"[{ts()}] Connected: {client.is_connected}  mtu={client.mtu_size}")
        for uuid, label in NOTIFY_CHANNELS:
            try:
                await client.start_notify(uuid, make_cb(label))
            except Exception as e:
                print(f"  subscribe {label}: {e}")
        await asyncio.sleep(0.3)

        print(f"[{ts()}] -> writing {len(payload)}B to {args.channel} "
              f"(response={use_response}, chunk={args.chunk})")
        await stream(client, char_uuid, payload,
                     response=use_response, chunk=args.chunk)
        print(f"[{ts()}] write complete; listening {args.listen_after}s...")
        await asyncio.sleep(args.listen_after)


if __name__ == "__main__":
    asyncio.run(main())
