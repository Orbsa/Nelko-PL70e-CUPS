#!/usr/bin/env python3
"""Connect to the Nelko PL70e-BT and dump its GATT tree."""

import asyncio
import sys

from bleak import BleakClient, BleakScanner

ADDRESS = "DC:0D:30:5A:A7:F5"  # LE address; BR/EDR is DC:1D:30:5A:A7:F5


PROP_KEYS = ("read", "write", "write-without-response", "notify", "indicate")


async def main():
    print(f"Scanning briefly for {ADDRESS}...")
    dev = await BleakScanner.find_device_by_address(ADDRESS, timeout=30.0)
    if dev is None:
        print("Not found. Make sure the printer is on and the iPhone is not actively connected.")
        sys.exit(1)
    print(f"Found: {dev.name} @ {dev.address}")

    async with BleakClient(dev) as client:
        print(f"Connected: {client.is_connected}")
        print()
        for service in client.services:
            print(f"[Service] {service.uuid}  {service.description}")
            for char in service.characteristics:
                props = ",".join(p for p in PROP_KEYS if p in char.properties)
                print(f"  [Char]  {char.uuid}  ({props})  handle={char.handle}")
                for desc in char.descriptors:
                    print(f"    [Desc] {desc.uuid}  handle={desc.handle}")


if __name__ == "__main__":
    asyncio.run(main())
