#!/usr/bin/env python3
"""
Probe the PL70e by writing test commands and logging anything the printer
sends on either of its notify channels.

Usage:
  python probe.py                    # run the built-in probe sequence
  python probe.py --raw 'BATTERY?'   # write a single command (CRLF auto-appended)
  python probe.py --hex 1b21 6f      # write raw bytes (no CRLF)
"""

import argparse
import asyncio
import sys
from datetime import datetime

from bleak import BleakClient

ADDRESS = "DC:0D:30:5A:A7:F5"

# Candidate write/notify pipes on this Feasycom/JieLi chip.
WRITE_FFF2 = "0000fff2-0000-1000-8000-00805f9b34fb"
NOTIFY_FFF1 = "0000fff1-0000-1000-8000-00805f9b34fb"

WRITE_ISSC = "49535343-8841-43f4-a8d4-ecbe34729bb3"
NOTIFY_ISSC_RX = "49535343-1e4d-4bd9-ba61-23c647249616"
NOTIFY_ISSC_CTL = "49535343-aca3-481c-91ec-d85e28a60318"  # also notify-capable

# Tencent / JieLi channel — looks like the live one.
WRITE_FEC7 = "0000fec7-0000-1000-8000-00805f9b34fb"
NOTIFY_FEC8 = "0000fec8-0000-1000-8000-00805f9b34fb"


def ts():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def render(b: bytes) -> str:
    try:
        s = b.decode("utf-8")
        if all(0x20 <= ch < 0x7F or ch in (0x09, 0x0A, 0x0D) for ch in b):
            return f"{s!r}  ({b.hex()})"
    except UnicodeDecodeError:
        pass
    return f"hex={b.hex()}"


def make_callback(label):
    def cb(_sender, data: bytearray):
        print(f"[{ts()}] <- {label:8s} {render(bytes(data))}")
    return cb


async def subscribe_all(client):
    for uuid, label in (
        (NOTIFY_FFF1, "fff1"),
        (NOTIFY_ISSC_RX, "issc_rx"),
        (NOTIFY_ISSC_CTL, "issc_ctl"),
        (NOTIFY_FEC8, "fec8"),
    ):
        try:
            await client.start_notify(uuid, make_callback(label))
            print(f"  subscribed: {label}")
        except Exception as e:
            print(f"  subscribe {label} FAILED: {e}")


async def write(client, uuid, data: bytes, label: str):
    print(f"[{ts()}] -> {label:8s} {render(data)}")
    try:
        # Many of these chips expect write-with-response on these chars.
        await client.write_gatt_char(uuid, data, response=True)
    except Exception as e:
        print(f"  write {label} FAILED: {e}")


async def run_default_probe(client):
    # Mirror the P21 vocabulary on every candidate pipe.
    cmds = [
        b"BATTERY?\r\n",
        b"CONFIG?\r\n",
        b"\x1b!?",        # ready status, no CRLF in P21
        b"\x1b!o\r\n",    # cancel pause / status, returns 16-byte struct
    ]
    pipes = [(WRITE_FEC7, "fec7"), (WRITE_FFF2, "fff2"), (WRITE_ISSC, "issc_tx")]
    for cmd in cmds:
        for uuid, label in pipes:
            await write(client, uuid, cmd, label)
            await asyncio.sleep(1.5)


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--raw", help="single command (CRLF auto-appended)")
    p.add_argument("--hex", help="raw hex bytes, e.g. 1b216f", default=None)
    p.add_argument("--channel", choices=["fff2", "issc", "fec7", "all"], default="all")
    p.add_argument("--listen", type=float, default=4.0,
                   help="seconds to wait after writes before disconnecting")
    args = p.parse_args()

    if args.raw is not None:
        payload = args.raw.encode() + b"\r\n"
    elif args.hex is not None:
        payload = bytes.fromhex(args.hex.replace(" ", ""))
    else:
        payload = None

    async with BleakClient(ADDRESS) as client:
        print(f"Connected: {client.is_connected}")
        await subscribe_all(client)

        if payload is None:
            await run_default_probe(client)
        else:
            channels = (
                [(WRITE_FEC7, "fec7"), (WRITE_FFF2, "fff2"), (WRITE_ISSC, "issc_tx")]
                if args.channel == "all"
                else [{
                    "fec7": (WRITE_FEC7, "fec7"),
                    "fff2": (WRITE_FFF2, "fff2"),
                    "issc": (WRITE_ISSC, "issc_tx"),
                }[args.channel]]
            )
            for uuid, label in channels:
                await write(client, uuid, payload, label)
                await asyncio.sleep(1.0)

        await asyncio.sleep(args.listen)


if __name__ == "__main__":
    asyncio.run(main())
