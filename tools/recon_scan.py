#!/usr/bin/env python3
"""List all BLE devices visible during a scan, with their advertised data."""

import asyncio

from bleak import BleakScanner


async def main():
    print("Scanning 15s...")
    devices = await BleakScanner.discover(timeout=15.0, return_adv=True)
    for addr, (dev, adv) in sorted(devices.items()):
        name = dev.name or adv.local_name or "?"
        rssi = adv.rssi
        services = ",".join(adv.service_uuids) if adv.service_uuids else "-"
        mfd = ",".join(f"{k:#06x}={v.hex()}" for k, v in adv.manufacturer_data.items()) or "-"
        print(f"{addr}  rssi={rssi:>4}  name={name!r}  svcs={services}  mfd={mfd}")


if __name__ == "__main__":
    asyncio.run(main())
