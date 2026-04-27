#!/usr/bin/env python3
"""CUPS backend for the Nelko PL70e-BT over BLE.

Device URI format: ble://AA-BB-CC-DD-EE-FF[?<query>]
(MAC uses dashes, not colons — CUPS's URI parser treats colons in the host
as port separators.)
Query keys (optional):
  channel=fff2|fec7|issc   default: fff2
  chunk=<int>              default: 180

CUPS calls this binary in two modes:
  argc == 1                discovery mode — print a 'direct' line on stdout, exit 0
  argc >= 6                print mode — send job via BLE; data on stdin or argv[6]

Status reporting goes to stderr as `STATE: ...`, `INFO: ...`, `ERROR: ...`.
Exit codes:
  0   success
  1   transient failure (CUPS will retry)
  2   bad job, hold for review
  4   no permission / can't talk to the device
"""

from __future__ import annotations

import asyncio
import os
import sys
from contextlib import suppress
from urllib.parse import parse_qs, urlparse

try:
    from bleak import BleakClient, BleakError, BleakScanner
except ImportError as e:  # pragma: no cover
    print(f"ERROR: bleak not available: {e}", file=sys.stderr)
    sys.exit(1)


WRITE_CHARS = {
    "fec7": ("0000fec7-0000-1000-8000-00805f9b34fb", True),   # write-with-response only
    "fff2": ("0000fff2-0000-1000-8000-00805f9b34fb", True),   # WNR supported but slow
    "issc": ("49535343-8841-43f4-a8d4-ecbe34729bb3", True),
}
NOTIFY_FEC8 = "0000fec8-0000-1000-8000-00805f9b34fb"

# Status bits mapped empirically against this hardware:
#   0x00 = idle, paper loaded
#   0x06 = paper out (0x04 is the real flag; 0x02 always rides with it on this
#          printer, presumably the spec's "ribbon end" stuck on for direct
#          thermal media)
#   0x20 = printing
# Other bits (cover open, jam, etc.) not yet observed.
STATUS_BITS: dict[int, tuple[str, str]] = {
    0x04: ("media-empty-error", "out of paper"),
    0x20: ("processing-job", "printing"),
}
# Bits that should hold the job before sending the raster.
PREFLIGHT_BLOCK_MASK = 0x04


def log(level: str, msg: str) -> None:
    """level is one of INFO, WARNING, ERROR, DEBUG."""
    print(f"{level}: {msg}", file=sys.stderr, flush=True)


def state(action: str, reason: str) -> None:
    """action is '+' to add or '-' to clear a state-reason."""
    print(f"STATE: {action}{reason}", file=sys.stderr, flush=True)


def discovery() -> None:
    # CUPS device-discovery format:
    # device-class scheme "make-and-model" "info" ["device-id"] ["location"]
    print('direct ble "Unknown" "Nelko PL70e-BT (BLE)" "MFG:Nelko;MDL:PL70e-BT;CMD:TSPL;"')


def parse_uri(uri: str):
    parsed = urlparse(uri)
    if parsed.scheme != "ble":
        raise ValueError(f"unexpected scheme {parsed.scheme!r}; need 'ble://...'")
    mac = parsed.netloc.upper().replace("-", ":")
    if len(mac) != 17 or mac.count(":") != 5:
        raise ValueError(f"could not parse MAC from {uri!r}")
    qs = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    channel = qs.get("channel", "fff2")
    if channel not in WRITE_CHARS:
        raise ValueError(f"unknown channel {channel!r}")
    chunk = int(qs.get("chunk", "180"))
    return mac, channel, chunk


def read_job(argv: list[str]) -> bytes:
    if len(argv) >= 7:
        with open(argv[6], "rb") as f:
            return f.read()
    return sys.stdin.buffer.read()


def decode_status(byte: int) -> list[tuple[str, str]]:
    """Return [(cups-state-reason, human), ...] for all set bits."""
    return [(reason, human) for mask, (reason, human) in STATUS_BITS.items() if byte & mask]


async def write_chunked(client: BleakClient, char_uuid: str, data: bytes,
                        *, response: bool, chunk: int, gap_ms: int = 5) -> None:
    for i in range(0, len(data), chunk):
        await client.write_gatt_char(char_uuid, data[i:i + chunk], response=response)
        if gap_ms:
            await asyncio.sleep(gap_ms / 1000)


async def find_device(mac: str, timeout: float = 30.0):
    """Return a BLEDevice or None. Bleak scans both legacy and extended advertising."""
    return await BleakScanner.find_device_by_address(mac, timeout=timeout)


async def print_job(uri: str, copies: int) -> int:
    mac, channel, chunk = parse_uri(uri)
    char_uuid, _ = WRITE_CHARS[channel]
    response = True  # all our channels support response writes; safer for now

    log("INFO", f"target={mac} channel={channel} chunk={chunk}")
    state("+", "connecting-to-device")
    device = await find_device(mac)
    if device is None:
        log("ERROR", "printer not found while scanning")
        state("+", "offline-report")
        return 1
    state("-", "connecting-to-device")

    last_status: int | None = None
    active_states: set[str] = set()

    def on_indicate(_sender: int, data: bytearray) -> None:
        nonlocal last_status
        b = bytes(data)
        if len(b) == 1:
            last_status = b[0]
            new_states = {r for r, _ in decode_status(b[0])}
            for r in active_states - new_states:
                state("-", r)
            for r in new_states - active_states:
                state("+", r)
            active_states.clear()
            active_states.update(new_states)

    try:
        async with BleakClient(device) as client:
            # MTU exchange — try to negotiate larger MTU for fewer round-trips.
            with suppress(Exception):
                await client._acquire_mtu()  # bleak-internal but reliable
            log("INFO", f"connected; mtu={client.mtu_size}")

            await client.start_notify(NOTIFY_FEC8, on_indicate)
            await asyncio.sleep(0.2)

            # Pre-flight status poll. Hold the job if the printer reports a
            # blocking condition (currently just paper-out).
            await client.write_gatt_char(char_uuid, b"\x1b!?", response=True)
            await asyncio.sleep(0.3)
            if last_status is not None:
                log("INFO", f"pre-flight status=0x{last_status:02x}")
                if last_status & PREFLIGHT_BLOCK_MASK:
                    log("ERROR", f"printer not ready (status=0x{last_status:02x})")
                    return 1

            data = read_job(sys.argv)
            log("INFO", f"sending {len(data)} bytes")
            for c in range(copies):
                if c > 0:
                    log("INFO", f"copy {c + 1}/{copies}")
                await write_chunked(client, char_uuid, data,
                                    response=response, chunk=chunk)
                # let the print engine settle / drain its receive buffer
                await asyncio.sleep(0.5)

            # Final status poll — log for empirical mapping.
            await client.write_gatt_char(char_uuid, b"\x1b!?", response=True)
            await asyncio.sleep(0.5)
            if last_status is not None:
                log("INFO", f"post-job status=0x{last_status:02x}")

            for r in list(active_states):
                state("-", r)
            log("INFO", "job complete")
            return 0

    except BleakError as e:
        log("ERROR", f"BLE error: {e}")
        return 1


def main() -> int:
    argv = sys.argv
    if len(argv) == 1:
        discovery()
        return 0

    if len(argv) < 6:
        log("ERROR", f"unexpected argv length {len(argv)}")
        return 1

    device_uri = os.environ.get("DEVICE_URI") or argv[0]
    try:
        copies = int(argv[4])
    except ValueError:
        copies = 1

    try:
        return asyncio.run(print_job(device_uri, copies))
    except Exception as e:  # pragma: no cover
        log("ERROR", f"unexpected backend failure: {e!r}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
