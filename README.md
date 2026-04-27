# nelko-pl70e-cups

Linux CUPS driver for the [Nelko PL70e-BT](https://nelko.com/products/nelko-bluetooth-thermal-shipping-label-printer-pl70e) 4×6" thermal
label printer over Bluetooth Low Energy. Connects directly via BLE

This was reverse-engineered against firmware `v3.0.1.407`. It bundles three
pieces:

- **`pl70e_ble.py`** — a CUPS backend that handles `ble://` URIs. Scans for the
  printer, connects, writes the rendered TSPL stream over GATT, and reports
  status back to CUPS.
- **vendor `rastertolabel` filter + PPD** — Nelko's official CUPS raster→TSPL
  converter, repackaged. Fetched at build/install time from Nelko's CDN; not
  redistributed in this repo.
- **`nelko-setup`** — interactive helper that scans for advertising printers
  and registers a CUPS queue with `lpadmin` for you.

## Hardware support

Tested on the **PL70e-BT**. The PL420 PPD is also installed and *should* work
(both are in the same TSPL family on the same Feasycom BLE module) but is
unverified. PRs welcome.

## Install

### NixOS (preferred)

Add the flake as an input and import the module:

```nix
# flake.nix
{
  inputs.nelko.url = "github:Orbsa/Nelko-PL70e-CUPS";

  outputs = { nixpkgs, nelko, ... }: {
    nixosConfigurations.myhost = nixpkgs.lib.nixosSystem {
      modules = [
        nelko.nixosModules.default
        ({ ... }: {
          services.nelko-pl70e = {
            enable = true;
            macAddress = "DC:0D:30:5A:A7:F5";   # your printer's BLE MAC (see below)
          };
        })
      ];
    };
  };
}
```

Then `sudo nixos-rebuild switch`. The module:

- Installs the driver package into `services.printing.drivers`.
- Enables `hardware.bluetooth`.
- Adds a polkit rule allowing the `lp` user to talk to BlueZ over D-Bus.
- Declaratively registers the queue via `hardware.printers.ensurePrinters`.

Available options (`services.nelko-pl70e.*`):

| Option | Default | Description |
|---|---|---|
| `enable` | `false` | Turn the module on |
| `macAddress` | *(required)* | BLE (LE) address of the printer |
| `name` | `"PL70e"` | CUPS queue name |
| `pageSize` | `"w288h432"` | Default PPD `PageSize` (4×6" = `w288h432`) |
| `channel` | `"fff2"` | GATT write characteristic (`fff2`, `fec7`, or `issc`) |
| `setAsDefault` | `false` | Make this the system-default printer |

### Other Linux distros

```sh
git clone https://github.com/Orbsa/nelko-pl70e-CUPS.git
cd nelko
sudo apt install cups bluez python3-bleak     # or your distro's equivalents
make fetch              # downloads the vendor .deb
sudo make install       # installs filter, PPDs, backend, nelko-setup CLI
sudo systemctl restart cups
```

You also need to allow the `lp` user (which CUPS workers run as) to talk to
BlueZ. Drop this in `/etc/polkit-1/rules.d/49-nelko-bluez.rules`:

```javascript
polkit.addRule(function(action, subject) {
  if (action.id.indexOf("org.bluez.") === 0 && subject.user === "lp") {
    return polkit.Result.YES;
  }
});
```

Then restart polkit (`sudo systemctl restart polkit`).

## First-time setup

Power on the printer and **make sure it's not connected to a phone** — only
one BLE central can hold the connection at a time. On iOS, that's
Settings → Bluetooth → tap the printer → *Disconnect* (not *Forget*).

Then:

```sh
nelko-setup
```

This scans for ~8 seconds, finds the printer by advertising name, and runs
`sudo lpadmin` to create a queue named `PL70e` pointed at it. The queue
defaults to 4×6" media (`w288h432`), which matches the printer's stock
label stock — `nelko-setup` with no flags is the right call for most users.

Common flags:

```sh
nelko-setup --name LabelPrinter --default
nelko-setup --mac DC:0D:30:5A:A7:F5         # skip scanning
nelko-setup --page-size Custom.50.8x25.4mm  # override the 4x6" default
```

After this, the queue persists in CUPS — every subsequent print is just:

```sh
lp -d PL70e label.pdf
```

## Finding the BLE MAC manually

The printer is dual-mode: the BR/EDR address you see paired with iOS is
**different** from the BLE address used by this driver. To find the BLE MAC
without `nelko-setup`:

```sh
bluetoothctl scan le        # printer must be powered, not phone-connected
```

Look for an entry like `PL70e-BT-XXXX` and use its address.

## Status reporting

The backend translates the printer's status byte to CUPS state-reasons.
Mapped so far on the PL70e-BT:

- `0x00` — idle, paper loaded
- `0x06` — out of paper (`media-empty-error` — the queue is held, not silently
  dropped)
- `0x20` — printing in progress

Other bits (cover open, jam, memory full) haven't been observed in the wild.
If you trigger one, please open an issue with the status byte from
`journalctl -u cups`.

## Troubleshooting

**`lpstat -p` shows the queue as stopped after a print fails.** That's CUPS's
auto-disable behavior. Fix the cause (paper, BT range, phone connection) and
run `cupsenable PL70e`.

**`Bad device-uri "ble://..."`.** The MAC must use **dashes** in the URI, not
colons — CUPS's URI parser interprets the first colon as a port separator.
The Nix module and `nelko-setup` handle this for you.

**Backend fails with `not found while scanning`.** Phone is connected, or the
printer is asleep, or out of range. The phone is the most common cause; see
*First-time setup*.

**`MTU=23` warning in logs.** Bleak's `_acquire_mtu()` is failing silently on
some kernels and the BLE link runs at the default 23-byte MTU. It still works,
just slower (a 4×6" page takes ~25s). Harmless.

## Development

The Nix flake provides a dev shell with bleak, btmon, wireshark, and the
recon scripts on PATH:

```sh
nix develop
python tools/recon_scan.py        # BLE scan
python tools/recon_gatt.py        # enumerate GATT services
python tools/dot_print.py 50 75   # quick dot-print test
```

Recon scripts that produced the protocol map are in `tools/`. The packet
captures used to derive everything aren't checked in — see `*.gitignore`.

## License

MIT, but **note** that the vendor `rastertolabel` binary and PPDs are
Nelko's proprietary code and are *not* under this license. They're fetched
from Nelko's official CDN at install time. If Nelko rehosts or removes the
file, the install will break until the URL is updated.
