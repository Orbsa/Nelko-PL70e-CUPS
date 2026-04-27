#!/usr/bin/env python3
"""Read the standard Device Information service from the printer."""

import asyncio

from bleak import BleakClient

ADDRESS = "DC:0D:30:5A:A7:F5"

DI_CHARS = {
    "00002a29-0000-1000-8000-00805f9b34fb": "Manufacturer Name",
    "00002a24-0000-1000-8000-00805f9b34fb": "Model Number",
    "00002a25-0000-1000-8000-00805f9b34fb": "Serial Number",
    "00002a27-0000-1000-8000-00805f9b34fb": "Hardware Revision",
    "00002a26-0000-1000-8000-00805f9b34fb": "Firmware Revision",
    "00002a28-0000-1000-8000-00805f9b34fb": "Software Revision",
    "00002a23-0000-1000-8000-00805f9b34fb": "System ID",
    "00002a2a-0000-1000-8000-00805f9b34fb": "IEEE Cert. List",
}


def show(label, data):
    try:
        s = data.decode("utf-8")
        printable = all(0x20 <= b < 0x7F or b in (0x09, 0x0A, 0x0D) for b in data)
        if printable:
            print(f"  {label:22s} {s!r}")
            return
    except UnicodeDecodeError:
        pass
    print(f"  {label:22s} hex={data.hex()}")


async def main():
    async with BleakClient(ADDRESS) as client:
        print(f"Connected: {client.is_connected}")
        for uuid, label in DI_CHARS.items():
            try:
                data = await client.read_gatt_char(uuid)
                show(label, data)
            except Exception as e:
                print(f"  {label:22s} <error: {e}>")

        print("\n-- Vendor read characteristics --")
        for uuid, label in [
            ("0000fec9-0000-1000-8000-00805f9b34fb", "Tencent fec9 (read)"),
            ("49535343-6daa-4d02-abf6-19569aca69fe", "ISSC config 6daa (read)"),
        ]:
            try:
                data = await client.read_gatt_char(uuid)
                show(label, data)
            except Exception as e:
                print(f"  {label:22s} <error: {e}>")


if __name__ == "__main__":
    asyncio.run(main())
